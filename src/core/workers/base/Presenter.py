class Presenter:
    def prepare_fail_view(self, *args, **kwargs):
        raise NotImplementedError

    def prepare_success_view(self, *args, **kwargs):
        raise NotImplementedError

    def prepare_progress_view(self, *args, **kwargs):
        raise NotImplementedError
