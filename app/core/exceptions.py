class IsolarError(Exception):
    """Base exception class for all iSolarCloud platform errors."""
    pass

class IsolarAuthenticationError(IsolarError):
    """Base exception for all authentication-related issues."""
    pass

class IsolarCredentialsError(IsolarAuthenticationError):
    """Exception raised when provided username or password is invalid."""
    pass

class IsolarServerSelectionError(IsolarAuthenticationError):
    """Exception raised when the selected server is incorrect or user does not exist on it."""
    pass

class IsolarTimeoutError(IsolarError):
    """Exception raised when an operation (navigation, element loading) times out."""
    pass

class IsolarUnexpectedPageError(IsolarError):
    """Exception raised when the page layout or URL is not what was expected."""
    pass

class IsolarNavigationError(IsolarError):
    """Base exception for all portal navigation issues."""
    pass

class IsolarNavigationTimeoutError(IsolarNavigationError):
    """Exception raised when navigating to menus or tabs times out."""
    pass

class IsolarReportPageNotFoundError(IsolarNavigationError):
    """Exception raised when critical report page elements (like tables or export buttons) are not visible."""
    pass

class IsolarMenuStructureChangedError(IsolarNavigationError):
    """Exception raised when expected menu layout or buttons are missing or renamed."""
    pass

class IsolarDownloadError(IsolarError):
    """Base exception for all download-related issues."""
    pass

class IsolarDownloadTimeoutError(IsolarDownloadError):
    """Exception raised when document download times out."""
    pass

class IsolarExportButtonNotFoundError(IsolarDownloadError):
    """Exception raised when the download export trigger button cannot be found."""
    pass

class IsolarInvalidDownloadedFileError(IsolarDownloadError):
    """Exception raised when the downloaded file fails Level 1 validation."""
    pass

class IsolarArchiveError(IsolarError):
    """Exception raised when file operations (moving/renaming) fail during archiving."""
    pass


