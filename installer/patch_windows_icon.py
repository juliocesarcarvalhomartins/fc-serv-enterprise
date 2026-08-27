from __future__ import annotations

import argparse
import struct
from pathlib import Path

import lief


def largest_ico_image(path: Path) -> tuple[dict[str, int], bytes]:
    data = path.read_bytes()
    reserved, image_type, count = struct.unpack_from("<HHH", data, 0)
    if reserved != 0 or image_type != 1 or count < 1:
        raise ValueError("Arquivo ICO inválido.")

    images: list[tuple[int, dict[str, int], bytes]] = []
    for index in range(count):
        offset = 6 + index * 16
        width, height, colors, reserved_byte, planes, bits, size, start = struct.unpack_from(
            "<BBBBHHII", data, offset
        )
        real_width = width or 256
        real_height = height or 256
        payload = data[start : start + size]
        if len(payload) != size:
            raise ValueError("Imagem interna do ICO está incompleta.")
        metadata = {
            "width": width,
            "height": height,
            "colors": colors,
            "reserved": reserved_byte,
            "planes": planes,
            "bits": bits,
        }
        images.append((real_width * real_height, metadata, payload))

    _, metadata, payload = max(images, key=lambda item: item[0])
    return metadata, payload


def patch_icon(executable: Path, icon_path: Path, output: Path) -> None:
    binary = lief.PE.parse(executable)
    if binary is None or not binary.has_resources:
        raise ValueError("O executável não possui recursos do Windows.")

    manager = binary.resources_manager
    if not manager.has_icons or not manager.icons:
        raise ValueError("O executável não possui um ícone para substituir.")

    metadata, payload = largest_ico_image(icon_path)
    old_icon = manager.icons[0]
    icon = lief.PE.ResourceIcon.from_serialization(old_icon.serialize())
    if not isinstance(icon, lief.PE.ResourceIcon):
        raise ValueError("Não foi possível preparar o novo ícone.")
    icon.id = old_icon.id
    icon.lang = old_icon.lang
    icon.sublang = old_icon.sublang
    icon.width = metadata["width"]
    icon.height = metadata["height"]
    icon.color_count = metadata["colors"]
    icon.reserved = metadata["reserved"]
    icon.planes = metadata["planes"]
    icon.bit_count = metadata["bits"]
    icon.pixels = memoryview(payload)
    manager.change_icon(old_icon, icon)
    binary.write(output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Substitui o ícone de um executável Windows.")
    parser.add_argument("executable", type=Path)
    parser.add_argument("icon", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    patch_icon(args.executable, args.icon, args.output)


if __name__ == "__main__":
    main()
