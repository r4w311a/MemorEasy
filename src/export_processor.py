import argparse
import csv
import glob
import json
import re
import shutil
import tempfile
import zipfile
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .media_processing import merge_jpg_with_overlay, merge_mp4_with_overlay
from .metadata import write_exif


JSON_PATH = "json/memories_history.json"
MEDIA_ROOT = "memories/"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S UTC"
MATCH_DELTAS = (0, -1, -2, 1, 2)


@dataclass
class MemoryMetadata:
    row_index: int
    date_utc: datetime
    media_type: str
    lat: str
    lon: str


@dataclass
class ZipMember:
    zip_path: Path
    member_name: str
    date_utc: datetime
    media_type: str
    source_key: str
    source_id: str
    extension: str


@dataclass
class MatchedMemory:
    metadata: MemoryMetadata
    media: ZipMember
    overlay: ZipMember | None
    matched_delta_seconds: int


def natural_zip_part(path: Path) -> tuple[str, int]:
    match = re.match(r"^(?P<base>.+?)(?:-(?P<part>\d+))?\.zip$", path.name)
    if not match:
        return (path.name, 0)
    part = int(match.group("part") or "1")
    return (match.group("base"), part)


def resolve_zip_inputs(inputs: list[str]) -> list[Path]:
    paths: list[Path] = []

    for raw_input in inputs:
        expanded = Path(raw_input).expanduser()
        if expanded.is_dir():
            paths.extend(expanded.glob("*.zip"))
            continue

        matches = glob.glob(str(expanded))
        if matches:
            paths.extend(Path(match) for match in matches)
        else:
            paths.append(expanded)

    zip_paths = sorted({path.resolve() for path in paths}, key=natural_zip_part)
    missing = [path for path in zip_paths if not path.exists()]
    if missing:
        missing_list = "\n".join(str(path) for path in missing)
        raise FileNotFoundError(f"Input ZIP(s) not found:\n{missing_list}")

    if not zip_paths:
        raise FileNotFoundError("No ZIP files found in the provided input.")

    return zip_paths


def parse_location(location: str) -> tuple[str, str]:
    match = re.search(r"([-0-9.]+),\s*([-0-9.]+)", location or "")
    if not match:
        raise ValueError(f"Location does not contain GPS coordinates: {location}")

    lat, lon = match.groups()
    lat_f = float(lat)
    lon_f = float(lon)
    if not (-90 <= lat_f <= 90 and -180 <= lon_f <= 180):
        raise ValueError(f"GPS coordinates are out of range: {lat}, {lon}")

    return lat, lon


def load_metadata(zip_paths: list[Path]) -> list[MemoryMetadata]:
    for zip_path in zip_paths:
        with zipfile.ZipFile(zip_path) as archive:
            if JSON_PATH not in archive.namelist():
                continue

            raw = json.loads(archive.read(JSON_PATH))
            rows = raw.get("Saved Media")
            if not isinstance(rows, list):
                raise ValueError(f"{JSON_PATH} does not contain a Saved Media list.")

            metadata: list[MemoryMetadata] = []
            for index, row in enumerate(rows):
                date_utc = datetime.strptime(row["Date"], DATE_FORMAT)
                lat, lon = parse_location(row.get("Location", ""))
                media_type = row.get("Media Type", "")
                if media_type not in {"Image", "Video"}:
                    raise ValueError(f"Unsupported media type at row {index}: {media_type}")
                metadata.append(
                    MemoryMetadata(
                        row_index=index,
                        date_utc=date_utc,
                        media_type=media_type,
                        lat=lat,
                        lon=lon,
                    )
                )
            return metadata

    raise FileNotFoundError(f"Could not find {JSON_PATH} in any input ZIP.")


def media_source_key(member_name: str, suffix: str) -> str:
    if not member_name.endswith(suffix):
        raise ValueError(f"Unexpected media member name: {member_name}")
    return member_name[: -len(suffix)]


def source_id_from_key(source_key: str) -> str:
    name = Path(source_key).name
    if "_" in name:
        return name.split("_", 1)[1]
    return name


def scan_zip_media(zip_paths: list[Path]) -> tuple[list[ZipMember], dict[str, ZipMember]]:
    media: list[ZipMember] = []
    overlays: dict[str, ZipMember] = {}

    for zip_path in zip_paths:
        with zipfile.ZipFile(zip_path) as archive:
            for info in archive.infolist():
                member = info.filename
                lower = member.lower()
                if not member.startswith(MEDIA_ROOT):
                    continue

                if lower.endswith("-main.jpg") or lower.endswith("-main.jpeg"):
                    extension = Path(member).suffix.lower()
                    source_key = media_source_key(member, f"-main{extension}")
                    media.append(
                        ZipMember(
                            zip_path=zip_path,
                            member_name=member,
                            date_utc=datetime(*info.date_time),
                            media_type="Image",
                            source_key=source_key,
                            source_id=source_id_from_key(source_key),
                            extension=extension,
                        )
                    )
                elif lower.endswith("-main.mp4"):
                    source_key = media_source_key(member, "-main.mp4")
                    media.append(
                        ZipMember(
                            zip_path=zip_path,
                            member_name=member,
                            date_utc=datetime(*info.date_time),
                            media_type="Video",
                            source_key=source_key,
                            source_id=source_id_from_key(source_key),
                            extension=".mp4",
                        )
                    )
                elif lower.endswith("-overlay.png"):
                    source_key = media_source_key(member, "-overlay.png")
                    overlays[source_key] = ZipMember(
                        zip_path=zip_path,
                        member_name=member,
                        date_utc=datetime(*info.date_time),
                        media_type="Overlay",
                        source_key=source_key,
                        source_id=source_id_from_key(source_key),
                        extension=".png",
                    )

    media.sort(key=lambda item: (item.date_utc, item.member_name))
    return media, overlays


def match_metadata_to_media(
    metadata_rows: list[MemoryMetadata],
    media_files: list[ZipMember],
    overlays: dict[str, ZipMember],
) -> tuple[list[MatchedMemory], list[MemoryMetadata], list[ZipMember]]:
    metadata_index: dict[tuple[datetime, str], deque[MemoryMetadata]] = defaultdict(deque)
    for row in metadata_rows:
        metadata_index[(row.date_utc, row.media_type)].append(row)

    matched: list[MatchedMemory] = []
    unmatched_media: list[ZipMember] = []

    for media in media_files:
        selected_metadata = None
        selected_delta = 0

        for delta in MATCH_DELTAS:
            key = (media.date_utc + timedelta(seconds=delta), media.media_type)
            candidates = metadata_index.get(key)
            if candidates:
                selected_metadata = candidates.popleft()
                selected_delta = delta
                break

        if not selected_metadata:
            unmatched_media.append(media)
            continue

        matched.append(
            MatchedMemory(
                metadata=selected_metadata,
                media=media,
                overlay=overlays.get(media.source_key),
                matched_delta_seconds=selected_delta,
            )
        )

    missing_metadata = [
        row
        for candidates in metadata_index.values()
        for row in candidates
    ]
    missing_metadata.sort(key=lambda row: row.date_utc, reverse=True)
    return matched, missing_metadata, unmatched_media


def copy_zip_member(member: ZipMember, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(member.zip_path) as archive:
        with archive.open(member.member_name) as source:
            with destination.open("wb") as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)


def extract_zip_member(member: ZipMember, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    copy_zip_member(member, destination)


def output_filename(match: MatchedMemory) -> str:
    prefix = match.metadata.date_utc.strftime("%Y-%m-%d-%H%M%S")
    source_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", match.media.source_id)
    extension = ".jpg" if match.media.extension.lower() in {".jpg", ".jpeg"} else ".mp4"
    return f"{prefix}_{source_id}{extension}"


def write_manifest(
    manifest_path: Path,
    rows: list[dict[str, str]],
) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "status",
        "output_file",
        "source_zip",
        "source_member",
        "date_utc",
        "media_type",
        "latitude",
        "longitude",
        "overlay_applied",
        "matched_delta_seconds",
        "message",
    ]
    with manifest_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_summary(
    summary_path: Path,
    summary: dict[str, object],
) -> None:
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8") as file:
        json.dump(summary, file, indent=2)
        file.write("\n")


def process_match(
    match: MatchedMemory,
    media_dir: Path,
    force: bool,
    skip_overlays: bool,
) -> tuple[dict[str, str], bool]:
    output_path = media_dir / output_filename(match)
    if output_path.exists() and not force:
        return (
            manifest_row(
                match,
                output_path,
                "skipped",
                "Output already exists",
                skip_overlays=skip_overlays,
            ),
            False,
        )

    if output_path.exists():
        output_path.unlink()

    try:
        if match.overlay and not skip_overlays:
            with tempfile.TemporaryDirectory(prefix="memoreasy-export-") as tmp:
                tmp_dir = Path(tmp)
                main_tmp = tmp_dir / Path(match.media.member_name).name
                overlay_tmp = tmp_dir / Path(match.overlay.member_name).name
                extract_zip_member(match.media, main_tmp)
                extract_zip_member(match.overlay, overlay_tmp)

                if match.media.media_type == "Image":
                    combined_path = merge_jpg_with_overlay(main_tmp, overlay_tmp)
                else:
                    combined_path = merge_mp4_with_overlay(main_tmp, overlay_tmp)

                if not combined_path:
                    raise RuntimeError("Overlay merge did not return an output path.")
                shutil.move(str(combined_path), output_path)
        else:
            copy_zip_member(match.media, output_path)

        date_str = match.metadata.date_utc.strftime(DATE_FORMAT)
        write_exif(output_path, date_str, match.metadata.lat, match.metadata.lon)
        return (
            manifest_row(
                match,
                output_path,
                "created",
                "",
                skip_overlays=skip_overlays,
            ),
            True,
        )

    except Exception as error:
        if output_path.exists():
            output_path.unlink()
        return (
            manifest_row(
                match,
                output_path,
                "failed",
                str(error),
                skip_overlays=skip_overlays,
            ),
            False,
        )


def manifest_row(
    match: MatchedMemory,
    output_path: Path,
    status: str,
    message: str,
    skip_overlays: bool = False,
) -> dict[str, str]:
    overlay_status = "yes" if match.overlay and not skip_overlays else "no"
    if match.overlay and skip_overlays:
        overlay_status = "skipped"

    return {
        "status": status,
        "output_file": str(output_path),
        "source_zip": str(match.media.zip_path),
        "source_member": match.media.member_name,
        "date_utc": match.metadata.date_utc.strftime(DATE_FORMAT),
        "media_type": match.metadata.media_type,
        "latitude": match.metadata.lat,
        "longitude": match.metadata.lon,
        "overlay_applied": overlay_status,
        "matched_delta_seconds": str(match.matched_delta_seconds),
        "message": message,
    }


def run_export(args: argparse.Namespace) -> int:
    zip_paths = resolve_zip_inputs(args.inputs)
    output_root = Path(args.output).expanduser().resolve()
    media_dir = output_root / "media"
    reports_dir = output_root / "reports"

    metadata_rows = load_metadata(zip_paths)
    media_files, overlays = scan_zip_media(zip_paths)
    matched, missing_metadata, unmatched_media = match_metadata_to_media(
        metadata_rows,
        media_files,
        overlays,
    )

    if args.limit:
        matched = matched[: args.limit]

    summary: dict[str, object] = {
        "input_zips": [str(path) for path in zip_paths],
        "output_root": str(output_root),
        "media_output": str(media_dir),
        "metadata_rows": len(metadata_rows),
        "main_media_files": len(media_files),
        "overlay_files": len(overlays),
        "skip_overlays": args.skip_overlays,
        "matched_media": len(matched),
        "missing_media_for_metadata_rows": len(missing_metadata),
        "unmatched_media_files": len(unmatched_media),
        "dry_run": args.dry_run,
        "limit": args.limit,
        "missing_metadata_rows": [
            {
                "row_index": row.row_index,
                "date_utc": row.date_utc.strftime(DATE_FORMAT),
                "media_type": row.media_type,
            }
            for row in missing_metadata
        ],
        "unmatched_media": [
            {
                "source_zip": str(media.zip_path),
                "source_member": media.member_name,
                "date_utc": media.date_utc.strftime(DATE_FORMAT),
                "media_type": media.media_type,
            }
            for media in unmatched_media
        ],
    }

    if args.dry_run:
        write_summary(reports_dir / "summary.json", summary)
        print_summary(summary, created=0, skipped=0, failed=0)
        return 0

    media_dir.mkdir(parents=True, exist_ok=True)

    manifest_rows: list[dict[str, str]] = []
    created = 0
    skipped = 0
    failed = 0

    for index, match in enumerate(matched, start=1):
        print(
            f"\rProcessing {index}/{len(matched)}: "
            f"{match.metadata.date_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC",
            end="",
            flush=True,
        )
        row, did_create = process_match(
            match,
            media_dir,
            args.force,
            args.skip_overlays,
        )
        manifest_rows.append(row)
        if row["status"] == "failed":
            failed += 1
            print(f"\nFailed: {row['source_member']} - {row['message']}")
        elif did_create:
            created += 1
        else:
            skipped += 1

    print()

    summary.update(
        {
            "created_files": created,
            "skipped_existing_files": skipped,
            "failed_files": failed,
        }
    )
    write_manifest(reports_dir / "manifest.csv", manifest_rows)
    write_summary(reports_dir / "summary.json", summary)
    print_summary(summary, created=created, skipped=skipped, failed=failed)
    return 1 if failed else 0


def print_summary(
    summary: dict[str, object],
    created: int,
    skipped: int,
    failed: int,
) -> None:
    print("\nMemorEasy export summary")
    print("=" * 50)
    print(f"Input ZIPs: {len(summary['input_zips'])}")
    print(f"Metadata rows: {summary['metadata_rows']}")
    print(f"Main media files: {summary['main_media_files']}")
    print(f"Overlay files: {summary['overlay_files']}")
    print(f"Skip overlays: {summary['skip_overlays']}")
    print(f"Matched media: {summary['matched_media']}")
    print(f"Missing media rows: {summary['missing_media_for_metadata_rows']}")
    print(f"Unmatched media files: {summary['unmatched_media_files']}")
    print(f"Created: {created}")
    print(f"Skipped: {skipped}")
    print(f"Failed: {failed}")
    print(f"Media output: {summary['media_output']}")
    print(f"Report: {summary['output_root']}/reports/summary.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Process Snapchat's new split Memories export ZIPs into a "
            "photo-library-ready media folder with timestamps, GPS metadata, "
            "and optional overlay layers applied."
        )
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="Snapchat export ZIP files, glob patterns, or directories containing ZIPs.",
    )
    parser.add_argument(
        "--output",
        default="./iphone_ready_memories",
        help="Output folder. Media will be written under OUTPUT/media.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite files that already exist in the output media folder.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze and write reports without extracting or modifying media.",
    )
    parser.add_argument(
        "--skip-overlays",
        action="store_true",
        help=(
            "Do not merge Snapchat overlay PNGs. Extract base JPG/MP4 media "
            "and write metadata only."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Process only the first N matched memories. Useful for testing.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(run_export(args))
