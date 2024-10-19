# SPDX-License-Identifier: GPL-2.0-or-later

from importlib import reload

should_reload = 'operators' in locals()
from . import (
  ui,
  keymaps,
  operators,
  properties,
)

if should_reload:
    properties = reload(properties)
    operators = reload(operators)
    keymaps = reload(keymaps)
    ui = reload(ui)


def register() -> None:
    ui.register()
    operators.register()
    keymaps.register()
    properties.register()


def unregister() -> None:
    properties.unregister()
    operators.unregister()
    keymaps.unregister()
    ui.unregister()
