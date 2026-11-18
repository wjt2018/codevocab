"""
从 ECDICT (https://github.com/skywind3000/ECDICT, MIT License) 生成 CodeVocab 内置单词本。

用法：
    python scripts/build_wordbooks.py <ecdict.csv 路径> [输出目录，默认 wordbooks] [--alpha]

默认按词频排序（常用词在前），加 --alpha 改为按字母顺序。

ECDICT 的 tag 字段里标了每个词属于哪些考试：
    zk 中考  gk 高考  cet4 四级  cet6 六级  ky 考研  ielts 雅思  toefl 托福  gre GRE
"""

import csv
import json
import re
import sys
from pathlib import Path

BOOKS = {
    # 输出文件名: (ECDICT 标签, 显示名称)
    "zhongkao": ("zk", "中考"),
    "gaokao": ("gk", "高考"),
    "cet4": ("cet4", "大学英语四级"),
    "cet6": ("cet6", "大学英语六级"),
    "kaoyan": ("ky", "考研"),
    "ielts": ("ielts", "雅思 IELTS"),
    "toefl": ("toefl", "托福 TOEFL"),
    "gre": ("gre", "GRE"),
}

# 统一词性写法：ECDICT 里形容词写作 a.，副词写作 ad.
POS_ALIASES = {"a": "adj", "ad": "adv", "pl": "n", "interj": "int"}
POS_NAMES = "vt|vi|v|n|adj|a|adv|ad|prep|conj|pron|int|interj|num|art|aux|pl|abbr|pref|suf"
POS_RE = re.compile(rf"^({POS_NAMES})\.\s*")
# 有些词条把多个词性写在同一行："vt. 剽窃；偷窃；vi. 窃取"
INLINE_POS_SPLIT = re.compile(rf"[；;,，]\s*(?=(?:{POS_NAMES})\.\s)")
SENSE_SPLIT = re.compile(r"\s*[,，;；]\s*")
BRACKET = re.compile(r"\[[^\]]*\]|［[^］]*］")

MAX_SENSES = 3  # 状态栏和朗读里每个单词最多保留几个义项


def convert_phonetic(p: str) -> str:
    """ECDICT 的音标用了西里尔字母 ә 和 ASCII 撇号，转成标准 IPA 字符。"""
    p = p.strip()
    if not p:
        return ""
    p = p.replace("ә", "ə").replace("'", "ˈ").replace(":", "ː").replace(",", "ˌ")
    return f"/{p}/"


def parse_translation(raw: str):
    """
    把 "vt. 放弃, 抛弃\\nn. 放任\\n[计] 放弃" 解析成 [(pos, [义项...]), ...]。
    带 [计]、[医] 这类领域标签的行是专业释义，放在最后，只在没有普通释义时才用。
    """
    lines = []
    for line in raw.replace("\\n", "\n").split("\n"):
        line = line.strip()
        if line:
            lines.extend(part.strip() for part in INLINE_POS_SPLIT.split(line) if part.strip())

    general, domain = [], []
    for line in lines:
        is_domain = line.startswith("[") or line.startswith("［")
        m = POS_RE.match(line)
        pos = None
        if m:
            name = m.group(1)
            pos = POS_ALIASES.get(name, name) + "."
            line = line[m.end():]
        senses = []
        for s in SENSE_SPLIT.split(BRACKET.sub("", line)):
            s = s.strip(" .。")
            if s and s not in senses:
                senses.append(s)
        if senses:
            (domain if is_domain else general).append((pos, senses))
    return general or domain


def build_entry(row):
    parsed = parse_translation(row["translation"])
    if not parsed:
        return None
    pos, senses = parsed[0]
    entry = {"word": row["word"].strip()}
    phonetic = convert_phonetic(row["phonetic"])
    if phonetic:
        entry["phonetic"] = phonetic
    if pos:
        entry["pos"] = pos
    entry["meaning"] = "；".join(senses[:MAX_SENSES])
    if len(parsed) > 1 or len(senses) > MAX_SENSES:
        entry["detail"] = "\n".join(f"{p} {'；'.join(s)}" if p else "；".join(s) for p, s in parsed)
    return entry


def freq_rank(row) -> int:
    """按当代语料库词频排序（越常用越靠前），没有词频的排在最后。"""
    for key in ("frq", "bnc"):
        try:
            value = int(row[key] or 0)
        except ValueError:
            value = 0
        if value > 0:
            return value
    return 10**9


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        sys.exit(__doc__)
    sort_mode = "alpha" if "--alpha" in sys.argv else "freq"
    src = Path(args[0])
    out_dir = Path(args[1]) if len(args) > 1 else Path(__file__).resolve().parent.parent / "wordbooks"
    out_dir.mkdir(parents=True, exist_ok=True)

    tag_to_book = {tag: name for name, (tag, _) in BOOKS.items()}
    rows = {name: [] for name in BOOKS}
    with src.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            for tag in row["tag"].split():
                if tag in tag_to_book:
                    rows[tag_to_book[tag]].append(row)

    for name, (_, title) in BOOKS.items():
        book_rows = rows[name]
        if sort_mode == "alpha":
            book_rows.sort(key=lambda r: r["word"].lower())
        else:
            book_rows.sort(key=lambda r: (freq_rank(r), r["word"].lower()))
        entries, seen = [], set()
        for row in book_rows:
            entry = build_entry(row)
            if entry and entry["word"].lower() not in seen:
                seen.add(entry["word"].lower())
                entries.append(entry)
        path = out_dir / f"{name}.json"
        # 每个单词一行，文件不会太大，也方便查看
        body = ",\n".join("  " + json.dumps(e, ensure_ascii=False) for e in entries)
        path.write_text("[\n" + body + "\n]\n", encoding="utf-8")
        print(f"{title:<12} {len(entries):>5} 词 -> {path}")


if __name__ == "__main__":
    main()
