# SPDX-License-Identifier: GPL-2.0-or-later

import bpy

addon_keymaps = []


def register() -> None:
    assert bpy.context
    if kc := bpy.context.window_manager.keyconfigs.addon:
        km = kc.keymaps.new(name='Node Editor', space_type="NODE_EDITOR")
        kmi = km.keymap_items.new("node.na_recenter_selected", type='G', value='PRESS', alt=True)
        kmi = km.keymap_items.new("node.na_arrange_selected", type='A', value='PRESS', ctrl=True)
        addon_keymaps.append((km, kmi))


def unregister() -> None:
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)

    addon_keymaps.clear()
