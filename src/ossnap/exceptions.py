class OSSnapError(Exception):
    pass

class ConfigNotFoundError(OSSnapError):
    pass

class GitError(OSSnapError):
    pass

class DecryptionError(OSSnapError):
    pass

class NetworkError(OSSnapError):
    pass

class GhNotInstalledError(OSSnapError):
    pass

class GhAuthError(OSSnapError):
    pass
