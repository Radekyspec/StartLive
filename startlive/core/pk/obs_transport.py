"""Select the StartLive OBS IPC backend without importing foreign OS APIs."""
import os


def create_media_connection(*, cancelled):
    if os.name == "nt":
        from .obs_pipe import ObsPipe
        return ObsPipe(cancelled=cancelled)
    from .obs_socket import ObsLocalSocket
    return ObsLocalSocket(cancelled=cancelled)
