# SPDX-License-Identifier: GPL-2.0-or-later

# type: ignore

from bpy.types import Context, Panel
from bpy.utils import register_class, unregister_class

from .utils import get_ntree


class NodePanel:
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Arrange"

    @classmethod
    def poll(cls, context: Context) -> bool:
        return context.space_data.type == 'NODE_EDITOR' and get_ntree() is not None


class NA_PT_ArrangeSelected(NodePanel, Panel):
    bl_label = "Arrange"

    def draw(self, context: Context) -> None:
        layout = self.layout
        settings = context.scene.na_settings

        layout.use_property_split = False
        layout.prop(settings, "arrange_mode", expand=True)
        layout.use_property_split = True
        if settings.arrange_mode == 'NODES':
            layout.operator("node.na_arrange_selected", text="Arrange Selected Nodes")
        else:
            layout.operator("node.na_batch_arrange")
        layout.prop(settings, "margin")

        header, panel = layout.panel("alignment", default_closed=True)
        header.label(text="Alignment")
        if panel:
            col = panel.column()
            col.prop(settings, "direction", text="Nodes")
            col.prop(settings, "socket_alignment", text="Sockets")

        header, panel = layout.panel("reroutes", default_closed=True)
        header.label(text="Reroutes")
        if panel:
            col = panel.column(heading="Reroutes")
            col.prop(settings, "keep_reroutes_outside_frames", text="Place Outside Frames")


class NA_PT_ClearLocations(NodePanel, Panel):
    bl_label = "Recenter"

    def draw(self, context: Context) -> None:
        layout = self.layout
        settings = context.scene.na_settings

        layout.use_property_split = False
        layout.prop(settings, "recenter_mode", expand=True)
        layout.use_property_split = True
        if settings.recenter_mode == 'NODES':
            layout.operator("node.na_recenter_selected", text="Recenter Selected Nodes")
        else:
            layout.operator("node.na_batch_recenter")
        layout.prop(settings, "origin")


classes = (
  NA_PT_ArrangeSelected,
  NA_PT_ClearLocations,
)


def register() -> None:
    for cls in classes:
        register_class(cls)


def unregister() -> None:
    for cls in reversed(classes):
        unregister_class(cls)
