class MacpackError(Exception):
    pass

class ConfigNotFoundError(MacpackError):
    pass

class GitError(MacpackError):
    pass

class DecryptionError(MacpackError):
    pass

class NetworkError(MacpackError):
    pass

class GhNotInstalledError(MacpackError):
    pass

class GhAuthError(MacpackError):
    pass
