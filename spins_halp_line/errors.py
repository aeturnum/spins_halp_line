
class WrapException(Exception):
    _NAME = "WrapException"

    def __init__(self, message, wrapped_exception=None):
        super(StoryNavigationException, self).__init__()
        self._message = message
        self.wrapped_exception = wrapped_exception

    @property
    def message(self):
        if not self.wrapped_exception:
            return f'{self._NAME}: {self._message}'
        else:
            return f'{self._NAME}: While attempting "{self._message}," encountered: {str(self.wrapped_exception)}'

    def __str__(self):
        return self.message

class StoryNavigationException(WrapException):
    _NAME = "StoryNavigationException"


class DataIntegrityError(WrapException):
    _NAME = "DataIntegrityError"