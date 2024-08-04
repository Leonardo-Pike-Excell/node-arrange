# SPDX-License-Identifier: GPL-2.0-or-later

from bpy.props import (
  BoolProperty,
  EnumProperty,
  IntVectorProperty,
  PointerProperty,
)
from bpy.types import PropertyGroup, Scene
from bpy.utils import (
  register_class,
  unregister_class,
)


class NA_PG_Settings(PropertyGroup):
    margin: IntVectorProperty(
      name="Margin",
      description="Spacing between nodes",
      default=(70, 70),
      min=0,
      options=set(),
      subtype='XYZ',
      size=2,
    )

    move_to_linked_y: BoolProperty(
      name="Move to Linked",
      description="Move nodes vertically towards their links",
      default=True,
      options=set(),
    )

    move_to_linked_y_type: EnumProperty(
      items=(('PARTIAL', "Partial", ""), ('FULL', "Full", "")),
      name="Mode",
      description="Mode",
      default='PARTIAL',
      options=set(),
    )


classes = [NA_PG_Settings]


def register():
    for cls in classes:
        register_class(cls)

    Scene.na_settings = PointerProperty(type=NA_PG_Settings)


def unregister():
    for cls in reversed(classes):
        if cls.is_registered:
            unregister_class(cls)

    del Scene.na_settings
