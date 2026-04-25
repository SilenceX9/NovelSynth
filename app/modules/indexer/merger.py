from app.models.context import GlobalContext, PartialContext, CharacterProfile, Foreshadow


def merge_contexts(partials: list[PartialContext], book_title: str) -> GlobalContext:
    """把多批 PartialContext 合并为一份 GlobalContext。"""
    char_map: dict[str, dict] = {}  # name → merged data
    all_foreshadows: dict[str, dict] = {}  # description → merged
    all_items: set[str] = set()
    all_plot: list[str] = []

    for partial in partials:
        # merge characters
        for c in partial.characters:
            name = c["name"]
            if name in char_map:
                existing = char_map[name]
                existing["chapters"] = sorted(set(existing["chapters"] + c.get("chapters", [])))
                existing["relationships"] = list(set(
                    existing["relationships"] + c.get("relationships", [])
                ))
            else:
                char_map[name] = {
                    "name": name,
                    "role": c.get("role", "其他"),
                    "relationships": c.get("relationships", []),
                    "chapters": c.get("chapters", []),
                }

        # merge plot (just append, chapters are sequential)
        all_plot.extend(partial.plot)

        # merge foreshadows
        for f in partial.foreshadows:
            desc = f["description"]
            if desc in all_foreshadows:
                # same foreshadow appeared again → likely resolved
                all_foreshadows[desc]["chapters"] = sorted(
                    set(all_foreshadows[desc]["chapters"] + f.get("chapters", []))
                )
                all_foreshadows[desc]["resolved"] = True
            else:
                all_foreshadows[desc] = {
                    "description": desc,
                    "chapters": f.get("chapters", []),
                    "resolved": False,
                }

        all_items.update(partial.key_items)

    total_chapters = max(
        (max(c["chapters"]) for c in char_map.values() if c["chapters"]),
        default=len(all_plot),
    )

    # downgrade characters that appear in < 3 chapters (unless 主角)
    characters = []
    for c in char_map.values():
        if c["role"] != "主角" and len(c["chapters"]) < 3:
            c["role"] = "其他"
        characters.append(CharacterProfile(
            name=c["name"],
            role=c["role"],
            relationships=c["relationships"],
            first_chapter=min(c["chapters"]) if c["chapters"] else 1,
            last_chapter=max(c["chapters"]) if c["chapters"] else 1,
        ))

    foreshadows = [
        Foreshadow(
            description=f["description"],
            setup_chapter=min(f["chapters"]) if f["chapters"] else 1,
            resolved=f["resolved"],
        )
        for f in all_foreshadows.values()
    ]

    return GlobalContext(
        book_title=book_title,
        total_chapters=total_chapters,
        characters=characters,
        main_plot=all_plot,
        foreshadows=foreshadows,
        key_items=sorted(all_items),
    )
