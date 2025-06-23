from .clickable_label import ClickableLabel
from .focus_aware_line_edit import FocusAwareLineEdit
from .pinyin_filter import CompletionComboBox
from .single_instance_window import SingleInstanceWindow
from .thread_safe_dict import ThreadSafeDict

from functools import partial
from json import dumps

dumps = partial(dumps, ensure_ascii=False, separators=(",", ":"))
