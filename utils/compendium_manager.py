import json
import argparse
from pathlib import Path
from collections import OrderedDict
from copy import deepcopy
from typing import Dict, Any

# ------------- Config -------------
KEEP_KEYS = {"label", "_id", "name", "tokenName", "description", "notes"}
TRANSLATABLE_KEYS = KEEP_KEYS
REDUCED_SUFFIX = ".reduced.json"

TOP_LEVEL_KEYS_ORDER = ["label", "mapping", "folders", "entries"]
KEYS_TO_SORT_IMMEDIATELY = {"folders", "entries"}
JSON_GLOB = "*.json"
# ----------------------------------

# -------- Reduce helpers ----------
def clean_entry(obj):
    """Reduce each entry recursively: keep only the keys in KEEP_KEYS."""
    if isinstance(obj, dict):
        new_obj = {}
        for k, v in obj.items():
            if k in KEEP_KEYS:
                new_obj[k] = v
            elif isinstance(v, (dict, list)):
                cleaned = clean_entry(v)
                if cleaned not in (None, {}, []):
                    new_obj[k] = cleaned
        return new_obj
    elif isinstance(obj, list):
        cleaned_list = [clean_entry(i) for i in obj]
        return [i for i in cleaned_list if i not in (None, {}, [])]
    else:
        return None

def reduce_entries(data):
    """Apply reduction only inside 'entries' while preserving outer structure."""
    if not isinstance(data, dict):
        return data
    result = {}
    for k, v in data.items():
        if k == "entries" and isinstance(v, dict):
            result[k] = {ek: clean_entry(ev) for ek, ev in v.items()}
        elif isinstance(v, (dict, list)):
            result[k] = reduce_entries(v)
        else:
            result[k] = v
    return result

def has_reduction(original, reduced):
    """Check if reduced differs from the original."""
    return json.dumps(original, sort_keys=True, ensure_ascii=False) != json.dumps(reduced, sort_keys=True, ensure_ascii=False)

def has_entries_nonempty(data):
    """Return True if there is a non-empty 'entries' dictionary anywhere."""
    if isinstance(data, dict):
        if isinstance(data.get("entries"), dict) and len(data["entries"]) > 0:
            return True
        return any(has_entries_nonempty(v) for v in data.values())
    if isinstance(data, list):
        return any(has_entries_nonempty(i) for i in data)
    return False

def has_translatable_list(data):
    """Return True if there is any list of dicts with keys that are translatable."""
    if isinstance(data, dict):
        for v in data.values():
            if has_translatable_list(v):
                return True
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                if any((k in item and k != "_id") for k in KEEP_KEYS):
                    return True
                if has_translatable_list(item):
                    return True
    return False
# ----------------------------------

# -------- Merge helpers -----------
def copy_string_fields(dst, src):
    """Copy only string fields from SRC into DST, limited to TRANSLATABLE_KEYS."""
    if not (isinstance(dst, dict) and isinstance(src, dict)):
        return
    for k, v in src.items():
        if k == "_id":
            continue
        if isinstance(v, str) and k in TRANSLATABLE_KEYS:
            dst[k] = v

def merge_translations(dst, src):
    """
    Merge translated/reduced SRC into the original DST:
    - Copies only string fields defined in TRANSLATABLE_KEYS (excluding '_id').
    - Recursively merges nested dicts and lists.
    - Merges lists by _id, then by name, then by index as fallback.
    - Cross-merges lists across keys within the same node.
    """
    if not (isinstance(dst, dict) and isinstance(src, dict)):
        return

    copy_string_fields(dst, src)

    for k, v in list(dst.items()):
        sv = src.get(k)
        if isinstance(v, dict) and isinstance(sv, dict):
            merge_translations(v, sv)
        elif isinstance(v, list) and isinstance(sv, list):
            merge_lists(v, sv)

    dst_lists = [v for v in dst.values() if isinstance(v, list)]
    src_lists = [v for v in src.values() if isinstance(v, list)]
    for dl in dst_lists:
        for sl in src_lists:
            if dl is not sl:
                merge_lists(dl, sl)

def merge_lists(dst_list, src_list):
    """
    Merge arrays of dict objects by matching items in this order:
    1) Match by '_id'
    2) Match by 'name'
    3) Fallback by index
    Does not create or remove items — only updates existing ones.
    """
    if not (isinstance(dst_list, list) and isinstance(src_list, list)):
        return

    dst_idx = [i for i, it in enumerate(dst_list) if isinstance(it, dict)]
    src_idx = [i for i, it in enumerate(src_list) if isinstance(it, dict)]

    by_id = {src_list[i].get("_id"): i for i in src_idx if isinstance(src_list[i].get("_id"), str)}
    by_name = {src_list[i].get("name"): i for i in src_idx if isinstance(src_list[i].get("name"), str)}

    used_src = set()

    for di in dst_idx:
        d = dst_list[di]
        sid = d.get("_id")
        if isinstance(sid, str) and sid in by_id:
            si = by_id[sid]
            if si not in used_src:
                merge_translations(d, src_list[si])
                used_src.add(si)

    for di in dst_idx:
        d = dst_list[di]
        if not isinstance(d.get("name"), str):
            continue
        si = by_name.get(d["name"])
        if si is not None and si not in used_src:
            merge_translations(d, src_list[si])
            used_src.add(si)

    rem_dst = [di for di in dst_idx if isinstance(dst_list[di], dict)]
    rem_src = [si for si in src_idx if si not in used_src]
    for di, si in zip(rem_dst, rem_src):
        merge_translations(dst_list[di], src_list[si])
        used_src.add(si)
# ----------------------------------

# -------- Sort helpers ------------
def sort_immediate_keys(data: Dict) -> Dict:
    """Sort only the first-level keys of a dict, keep values intact."""
    if not isinstance(data, dict):
        return data
    sorted_items = sorted(data.items(), key=lambda item: item[0])
    return OrderedDict(sorted_items)

def partial_sort_json(data: Dict) -> Dict:
    """
    Apply sorting rules:
    1) Keep top-level key order as TOP_LEVEL_KEYS_ORDER (when present).
    2) For 'folders' and 'entries', sort immediate inner keys only.
    """
    sorted_data = OrderedDict()

    for key in TOP_LEVEL_KEYS_ORDER:
        if key in data:
            value = data[key]
            if key in KEYS_TO_SORT_IMMEDIATELY and isinstance(value, dict):
                sorted_data[key] = sort_immediate_keys(value)
            else:
                sorted_data[key] = value

    for key, value in data.items():
        if key not in TOP_LEVEL_KEYS_ORDER:
            sorted_data[key] = value

    return sorted_data

def process_json_file_for_sort(json_file: Path):
    """Load, partially sort keys, and save a JSON file."""
    try:
        with json_file.open(encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            sorted_data = partial_sort_json(data)
        else:
            print(f"[sort] skip (not a top-level JSON object): {json_file.name}")
            return

        with json_file.open("w", encoding="utf-8") as f:
            json_str = json.dumps(sorted_data, ensure_ascii=False, indent=2)
            f.write(json_str)

        print(f"[sort] updated: {json_file.name}")

    except json.JSONDecodeError:
        print(f"[sort] invalid JSON: {json_file.name}")
    except Exception as e:
        print(f"[sort] error {json_file.name}: {e}")
# ----------------------------------

# ------------- I/O & CLI ----------
def find_compendium_dir():
    """Locate the 'compendium/pt-BR' directory relative to this script."""
    here = Path(__file__).resolve().parent
    candidates = [here / "compendium" / "pt-BR", here.parent / "compendium" / "pt-BR"]
    for p in candidates:
        if p.exists():
            return p
    return None

def reduce_directory(compendium_dir: Path):
    """Create *.reduced.json files with minimized translatable content."""
    for json_file in compendium_dir.glob(JSON_GLOB):
        if json_file.suffix != ".json" or json_file.name.endswith(REDUCED_SUFFIX):
            continue
        try:
            with json_file.open(encoding="utf-8") as f:
                data = json.load(f)

            if not has_entries_nonempty(data):
                print(f"[reduce] skip (no 'entries'): {json_file.name}")
                continue
            if not has_translatable_list(data):
                print(f"[reduce] skip (no translatable list): {json_file.name}")
                continue

            reduced = reduce_entries(deepcopy(data))
            if has_reduction(data, reduced):
                out_path = json_file.with_name(json_file.stem + REDUCED_SUFFIX)
                with out_path.open("w", encoding="utf-8") as f:
                    json.dump(reduced, f, ensure_ascii=False, indent=2)
                print(f"[reduce] wrote: {out_path.name}")
            else:
                print(f"[reduce] no changes: {json_file.name}")
        except Exception as e:
            print(f"[reduce] error {json_file.name}: {e}")

def merge_directory(compendium_dir: Path):
    """Merge *.reduced.json translations into original JSON files."""
    for json_file in compendium_dir.glob(JSON_GLOB):
        if json_file.suffix != ".json" or json_file.name.endswith(REDUCED_SUFFIX):
            continue
        reduced_path = json_file.with_name(json_file.stem + REDUCED_SUFFIX)
        if not reduced_path.exists():
            continue
        try:
            with json_file.open(encoding="utf-8") as f:
                original = json.load(f)
            with reduced_path.open(encoding="utf-8") as f:
                translated = json.load(f)

            if isinstance(original, dict) and isinstance(translated, dict):
                copy_string_fields(original, translated)

                o_entries = original.get("entries")
                t_entries = translated.get("entries")
                if isinstance(o_entries, dict) and isinstance(t_entries, dict):
                    t_by_key = {k: v for k, v in t_entries.items() if isinstance(v, dict)}
                    t_by_inner_name = {}
                    for tk, tv in t_entries.items():
                        if isinstance(tv, dict):
                            nm = tv.get("name")
                            if isinstance(nm, str):
                                t_by_inner_name[nm] = tv

                    for key, o_val in o_entries.items():
                        if not isinstance(o_val, dict):
                            continue

                        t_val = t_by_key.get(key)

                        if t_val is None:
                            oname = o_val.get("name")
                            if isinstance(oname, str):
                                t_val = t_by_key.get(oname)

                        if t_val is None:
                            oname = o_val.get("name")
                            if isinstance(oname, str):
                                t_val = t_by_inner_name.get(oname)

                        if isinstance(t_val, dict):
                            merge_translations(o_val, t_val)

                    with json_file.open("w", encoding="utf-8") as f:
                        json.dump(original, f, ensure_ascii=False, indent=2)
                    print(f"[merge] updated: {json_file.name}")
                else:
                    print(f"[merge] skipped (no 'entries'): {json_file.name}")
        except Exception as e:
            print(f"[merge] error {json_file.name}: {e}")

def purge_reduced(compendium_dir: Path):
    """Delete all *.reduced.json files in the compendium directory."""
    count = 0
    for reduced_file in compendium_dir.glob(f"*{REDUCED_SUFFIX}"):
        try:
            reduced_file.unlink()
            count += 1
            print(f"[purge] deleted: {reduced_file.name}")
        except Exception as e:
            print(f"[purge] error {reduced_file.name}: {e}")
    if count == 0:
        print("[purge] nothing to delete")

def sort_directory(compendium_dir: Path):
    """Partially sort keys for all JSON files (skip *.reduced.json)."""
    for json_file in compendium_dir.glob(JSON_GLOB):
        if json_file.suffix == ".json" and not json_file.name.endswith(REDUCED_SUFFIX):
            process_json_file_for_sort(json_file)
# ----------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Reduce, merge, purge, or sort translation JSONs for Foundry compendia."
    )
    parser.add_argument(
        "--mode",
        choices=["reduce", "merge", "purge", "sort"],
        default="sort",
        help="Operation to perform"
    )
    args = parser.parse_args()

    compendium_dir = find_compendium_dir()
    if not compendium_dir:
        print("Directory 'compendium/pt-BR' not found relative to this script.")
        return

    if args.mode == "reduce":
        reduce_directory(compendium_dir)
    elif args.mode == "merge":
        merge_directory(compendium_dir)
    elif args.mode == "purge":
        purge_reduced(compendium_dir)
    else:
        sort_directory(compendium_dir)

if __name__ == "__main__":
    main()
