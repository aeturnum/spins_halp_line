import traceback


class WrapException(Exception):
    _NAME = "WrapException"

    def __init__(self, message, wrapped_exception: Exception=None):
        super(WrapException, self).__init__()
        self._message = message
        self.wrapped_exception = wrapped_exception

    @property
    def message(self):
        if not self.wrapped_exception:
            return f'{self._NAME}: {self._message}:'
        else:
            s = f'{self._NAME}: While attempting "{self._message}", got exception {self.wrapped_exception}:'
            s += "\n".join(traceback.extract_tb(self.wrapped_exception.__traceback__).format())
            return s

    def __str__(self):
        return self.message


class StoryNavigationException(WrapException):
    _NAME = "StoryNavigationException"


class DataIntegrityError(WrapException):
    _NAME = "DataIntegrityError"
