class CodeMindError(Exception):
    pass

class GitHubAPIError(CodeMindError):
    pass

class AIProviderError(CodeMindError):
    pass

class WebhookValidationError(CodeMindError):
    pass

