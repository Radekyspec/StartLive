from startlive.core.workers.base.CallbackPresenter import CallbackPresenter

# Assignment rather than an alias import: an import optimizer must not empty
# this module, because every PK adapter imports PkPresenter from here.
PkPresenter = CallbackPresenter
