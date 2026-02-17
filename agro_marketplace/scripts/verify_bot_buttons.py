#!/usr/bin/env python3
"""Static verification that bot button callbacks/texts have handlers."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOT = ROOT / "src" / "bot"
HANDLERS = BOT / "handlers"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


button_callbacks: set[str] = set()
button_texts: set[str] = set()
for py in BOT.rglob("*.py"):
    src = read(py)
    for m in re.finditer(r'kb\.button\(text="([^"]+)"[^\n]*\)', src):
        full = m.group(0)
        text = m.group(1)
        cb = re.search(r'callback_data\s*=\s*f?"([^"]+)"', full)
        if cb:
            val = cb.group(1)
            if "{" in val:
                val = val.split("{", 1)[0]
            button_callbacks.add(val)
        else:
            button_texts.add(text)

# InlineKeyboardButton constructions too
for py in HANDLERS.rglob("*.py"):
    src = read(py)
    for m in re.finditer(r'InlineKeyboardButton\([^\)]*callback_data\s*=\s*f?"([^"]+)"', src):
        val = m.group(1)
        if "{" in val:
            val = val.split("{", 1)[0]
        button_callbacks.add(val)

handler_eq: set[str] = set()
handler_sw: set[str] = set()
handler_text: set[str] = set()
for py in HANDLERS.rglob("*.py"):
    src = read(py)
    handler_eq.update(re.findall(r'F\.data\s*==\s*"([^"]+)"', src))
    handler_sw.update(re.findall(r'F\.data\.startswith\("([^"]+)"\)', src))
    handler_text.update(re.findall(r'F\.text\s*==\s*"([^"]+)"', src))

missing_callbacks: list[str] = []
for cb in sorted(button_callbacks):
    if cb in handler_eq:
        continue
    if any(cb.startswith(prefix) for prefix in handler_sw):
        continue
    missing_callbacks.append(cb)

# Some reply buttons are consumed by FSM free-text handlers without F.text checks.
text_exempt = {
    "⏭ Пропустити",
    "⬅️ Назад",
    "✏️ Вписати свій район",
    "👨‍🌾 Фермер",
    "🧑‍💼 Покупець",
    "🚚 Логіст",
}
missing_texts = sorted(t for t in button_texts if t not in handler_text and t not in text_exempt)

if missing_callbacks or missing_texts:
    print("❌ Button coverage check failed")
    if missing_callbacks:
        print("Missing callback handlers:")
        for item in missing_callbacks:
            print(f"  - {item}")
    if missing_texts:
        print("Missing text handlers:")
        for item in missing_texts:
            print(f"  - {item}")
    raise SystemExit(1)

print("✅ All discovered bot buttons have handlers")
