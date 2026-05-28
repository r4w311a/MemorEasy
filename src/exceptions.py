# =========================================================================== #

class MemorEasyError(Exception):
    """Base exception for MemorEasy errors"""
    pass


class DependencyError(MemorEasyError):
    """Raised when required tools (exiftool, ffmpeg) are missing"""
    pass


class ImageProcessingError(MemorEasyError):
    """Raised when image processing fails"""
    pass


class VideoProcessingError(MemorEasyError):
    """Raised when video processing fails"""
    pass

# =========================================================================== #
