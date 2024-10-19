# SPDX-License-Identifier: GPL-2.0-or-later

import bpy

addon_keymaps = []


def register() -> None:
    if kc := bpy.context.window_manager.keyconfigs.addon:
        km = kc.keymaps.new(name='Node Editor', space_type="NODE_EDITOR")
        kmi = km.keymap_items.new("node.na_clear_locations", type='G', value='PRESS', alt=True)
        addon_keymaps.append((km, kmi))


def unregister() -> None:
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)

    addon_keymaps.clear()
