class PickerError(RuntimeError):
    """Base Picker exception."""


class PickerConfigurationError(PickerError):
    pass


class PickerTimeoutError(PickerError):
    pass


class PickerProviderError(PickerError):
    pass


class PickerStructuredOutputError(PickerError):
    pass
