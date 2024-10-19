# SPDX-License-Identifier: GPL-2.0-or-later

from bpy.types import Context, Panel
from bpy.utils import register_class, unregister_class


class NodePanel:
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Arrange"


class NA_PT_ArrangeSelected(NodePanel, Panel):
    bl_label = "Arrange"

    def draw(self, context: Context) -> None:
        layout = self.layout
        layout.use_property_split = True

        scene = context.scene
        settings = scene.na_settings

        layout.operator("node.na_arrange_selected")

        layout.prop(settings, "margin")


class NA_PT_ClearLocations(NodePanel, Panel):
    bl_label = "Clear"

    def draw(self, context: Context) -> None:
        layout = self.layout

        layout.operator("node.na_clear_locations")


classes = [NA_PT_ArrangeSelected, NA_PT_ClearLocations]


def register() -> None:
    for cls in classes:
        register_class(cls)


def unregister() -> None:
    for cls in reversed(classes):
        if cls.is_registered:
            unregister_class(cls)
