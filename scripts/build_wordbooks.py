"""
从 ECDICT (https://github.com/skywind3000/ECDICT, MIT License) 生成 CodeVocab 内置单词本，
美式音标来自 CMUdict (https://github.com/cmusphinx/cmudict, BSD 风格许可证)。

用法：
    python scripts/build_wordbooks.py <ecdict.csv 路径> <cmudict.dict 路径> [输出目录，默认 wordbooks] [--alpha]

每个词条的 phonetic 是英式音标（ECDICT），phonetic_us 是美式音标（CMUdict 转换成 IPA）。

默认按词频排序（常用词在前），加 --alpha 改为按字母顺序。
过于基础的词（中考词汇中词频最高的部分，以及月份、国名等首字母大写的词）不会放进考试词库，规则见 is_basic()。

ECDICT 的 tag 字段里标了每个词属于哪些考试：
    zk 中考  gk 高考  cet4 四级  cet6 六级  ky 考研  ielts 雅思  toefl 托福  gre GRE

另外会根据人工整理的词表生成专业词库，释义使用词表里的专业含义，音标和通用释义从 ECDICT 补充：
    scripts/programmer_words.tsv -> 程序员词汇（programmer.json）
    scripts/business_words.tsv   -> 商务英语（business.json）
    scripts/mispronounced_words.tsv -> 程序员易读错词（mispronounced.json，音标和误读说明均为人工标注）
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

# 过于基础的词（the、in、go、make、good……）不放进考试词库：
# 中考词汇里词频排在前 BASIC_RANK 名的词，以及首字母大写的词（月份、星期、国名等）。
BASIC_RANK = 1000


# ECDICT 考试标签里的个别脏数据
WORD_FIXES = {"reservior": "reservoir"}  # 拼写错误 -> 正确拼写
EXCLUDED_WORDS = {
    "cance",  # 高考标签下的人名（坎斯）
    "vcd",  # 释义是“可变电容二极体”，不是影碟
}


def is_basic(row) -> bool:
    word = row["word"]
    return word[:1].isupper() or ("zk" in row["tag"].split() and freq_rank(row) <= BASIC_RANK)


def convert_phonetic(p: str) -> str:
    """
    ECDICT 的音标用了西里尔字母 ә、ASCII 撇号和点号，转成标准 IPA 字符：
    - 有多个读音时写成 "liːd. led"，只取第一个
    - 次重音写作 "." 或 ","，转成 ˌ
    """
    p = p.strip()
    if not p:
        return ""
    p = re.split(r"[.;,]\s+", p)[0].strip()
    p = p.replace("ә", "ə").replace("'", "ˈ").replace(":", "ː").replace(",", "ˌ").replace(".", "ˌ")
    return f"/{p}/"


# ---------------------------------------------------------------------------
# 音标：ECDICT 没有音标的词，先查人工补充表，再尝试从词根推导
# ---------------------------------------------------------------------------

OVERRIDES_TSV = Path(__file__).resolve().parent / "phonetic_overrides.tsv"

# 英美拼写差异：(词尾, 替换成)
SPELLING_VARIANTS = [("re", "er"), ("our", "or"), ("ise", "ize"), ("yse", "yze"), ("sy", "zy"), ("ggon", "gon"), ("l", "ll")]
SIBILANTS = ("s", "z", "ʃ", "ʒ", "tʃ", "dʒ")
VOICELESS = ("p", "t", "k", "f", "θ", "s", "ʃ", "tʃ")


def _last_sound(ipa: str) -> str:
    return ipa.strip("/").rstrip("ː ")


def plural_sound(ipa: str) -> str:
    """-s 的读音：咝音后读 /iz/，清辅音后读 /s/，其他读 /z/。"""
    last = _last_sound(ipa)
    if last.endswith(SIBILANTS):
        return "iz"
    return "s" if last.endswith(VOICELESS) else "z"


def past_sound(ipa: str) -> str:
    """-ed 的读音：t/d 后读 /id/，清辅音后读 /t/，其他读 /d/。"""
    last = _last_sound(ipa)
    if last.endswith(("t", "d")):
        return "id"
    return "t" if last.endswith(VOICELESS) else "d"


def append_sound(ipa: str, sound: str) -> str:
    """在词根音标后加上后缀读音。单音节词根没有重音符号，加上后缀变成多音节后要补上重音。"""
    base = ipa.strip("/")
    if "ˈ" not in base and " " not in base and re.search(r"[aeiouəɪʊɒʌæɜɔ]", sound):
        base = "ˈ" + base
    return f"/{base}{sound}/"


def load_overrides(path: Path):
    overrides = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            word, phonetic = (p.strip() for p in line.split("\t")[:2])
            overrides[word.lower()] = phonetic
    return overrides


class PhoneticIndex:
    """查询音标：ECDICT → 人工补充表 → 自动推导（词形变化、拼写变体、合成词、常见后缀）。"""

    def __init__(self, overrides):
        self.overrides = overrides
        self.raw = {}  # 小写单词 -> (ECDICT 原始音标, 词形变化)
        self.derived = 0

    def add(self, row):
        word = row["word"].lower()
        phonetic = row["phonetic"].strip()
        if word not in self.raw or (phonetic and not self.raw[word][0]):
            self.raw[word] = (phonetic, row["exchange"])

    def lookup(self, word: str, derive: bool = True) -> str:
        w = word.lower()
        raw = self.raw.get(w)
        result = (convert_phonetic(raw[0]) if raw and raw[0] else "") or self.overrides.get(w, "")
        if not result and derive:
            result = self._derive(w)
            self.derived += bool(result)
        return result

    def _derive(self, w: str) -> str:
        # 1. 词形变化：ECDICT 的 exchange 字段里，0 是原形，1 是变化类型（s 复数 / p d 过去式 / i 现在分词 / r t 比较级最高级）
        exchange = (self.raw.get(w) or ("", ""))[1]
        if exchange:
            ex = dict(x.split(":", 1) for x in exchange.split("/") if ":" in x)
            lemma, kinds = ex.get("0", ""), ex.get("1", "")
            base = self.lookup(lemma, derive=False) if lemma and lemma.lower() != w else ""
            if base:
                for kind in kinds:
                    if kind in "s3":
                        return append_sound(base, plural_sound(base))
                    if kind in "pd":
                        return append_sound(base, past_sound(base))
                    if kind == "i":
                        return append_sound(base, "iŋ")
                    if kind == "r":
                        return append_sound(base, "ə")
                    if kind == "t":
                        return append_sound(base, "ist")
                return base
        # 2. 英美拼写差异：theatre -> theater
        for ending, replacement in SPELLING_VARIANTS:
            if w.endswith(ending):
                found = self.lookup(w[: -len(ending)] + replacement, derive=False)
                if found:
                    return found
        # 3. 合成词：well-known、ice cream
        if re.search(r"[- ]", w):
            parts = [p for p in re.split(r"[- ]", w) if p]
            found = [self.lookup(p) for p in parts]
            if all(found):
                return "/" + " ".join(p.strip("/") for p in found) + "/"
            return ""
        # 4. 常见后缀：(后缀, 可能的词根, 后缀读音)
        doubled = w[:-4] if len(w) > 5 and w[-4] == w[-5] else None  # planning -> plan
        rules = [
            ("ily", [w[:-3] + "y"], "li"),
            ("bly", [w[:-1] + "e"], "i"),
            ("ly", [w[:-2]], "li"),
            ("iness", [w[:-5] + "y"], "nis"),
            ("ness", [w[:-4]], "nis"),
            ("ment", [w[:-4]], "mənt"),
            # 先试“去掉后缀再补 e”（muted -> mute），避免匹配到更短的无关词（mut）
            ("ing", [w[:-3] + "e", w[:-3], doubled], "iŋ"),
            ("ed", [w[:-1], w[:-2], w[:-3] if len(w) > 4 and w[-3] == w[-4] else None], None),
            ("er", [w[:-1], w[:-2]], "ə"),
            # 先试 -s 再试 -es（sales -> sale，而不是 sal）
            ("s", [w[:-1]], None),
            ("es", [w[:-2]], None),
        ]
        for suffix, stems, sound in rules:
            if not w.endswith(suffix):
                continue
            for stem in stems:
                base = self.lookup(stem, derive=False) if stem else ""
                if base:
                    if sound is None:
                        sound = past_sound(base) if suffix == "ed" else plural_sound(base)
                    return append_sound(base, sound)
        return ""


# ---------------------------------------------------------------------------
# 美式音标：CMUdict 的 ARPAbet 转成 IPA
# ---------------------------------------------------------------------------

US_OVERRIDES_TSV = Path(__file__).resolve().parent / "phonetic_us_overrides.tsv"

# 元音后面的数字是重音：1 主重音，2 次重音，0 不重读
ARPABET_VOWELS = {
    "AA": "ɑː", "AE": "æ", "AH": "ʌ", "AO": "ɔː", "AW": "aʊ", "AY": "aɪ", "EH": "e", "ER": "ɝː",
    "EY": "eɪ", "IH": "ɪ", "IY": "iː", "OW": "oʊ", "OY": "ɔɪ", "UH": "ʊ", "UW": "uː",
}
# 不重读时的写法：AH0 是 /ə/，ER0 是 /ɚ/，happy 结尾的 IY0 是 /i/
ARPABET_UNSTRESSED = {"AH": "ə", "ER": "ɚ", "IY": "i", "UW": "u"}
ARPABET_CONSONANTS = {
    "B": "b", "CH": "tʃ", "D": "d", "DH": "ð", "F": "f", "G": "g", "HH": "h", "JH": "dʒ", "K": "k",
    "L": "l", "M": "m", "N": "n", "NG": "ŋ", "P": "p", "R": "r", "S": "s", "SH": "ʃ", "T": "t",
    "TH": "θ", "V": "v", "W": "w", "Y": "j", "Z": "z", "ZH": "ʒ",
}
# 英语里能放在音节开头的辅音组合，用来切分音节、确定重音符号的位置
ONSETS = {
    *[(c,) for c in ARPABET_CONSONANTS if c != "NG"],
    *[(c, "R") for c in ("P", "B", "T", "D", "K", "G", "F", "TH", "SH")],
    *[(c, "L") for c in ("P", "B", "K", "G", "F", "S")],
    *[(c, "W") for c in ("T", "D", "K", "G", "S", "TH")],
    *[("S", c) for c in ("P", "T", "K", "M", "N")],  # 不含 sf：transfer 是 /trænsˈfɝː/，不是 /trænˈsfɝː/
    *[(c, "Y") for c in ("P", "B", "K", "G", "F", "V", "M", "HH")],
    ("S", "P", "R"), ("S", "T", "R"), ("S", "K", "R"), ("S", "P", "L"), ("S", "K", "W"), ("S", "K", "Y"),
}


def arpabet_to_ipa(phones) -> str:
    """
    把 ["K", "AH0", "M", "P", "Y", "UW1", "T", "ER0"] 转成 /kəmˈpjuːtɚ/。
    - 元音之间的辅音按“最大首音”原则分给后一个音节，重音符号标在音节开头
    - 单音节词不标重音；有多个主重音时，以最后一个为主重音，前面的改为次重音
    - 主重音之后、以及紧挨在主重音前面的次重音不标（与常见词典一致：ignore 写作 /ɪgˈnɔːr/）
    - 不重读的 ER 后面紧跟元音时拆成 /ə/ + /r/，r 归下一个音节（array /əˈreɪ/，而不是 /ɚˈeɪ/）
    - 词尾的 IY 写作 /i/（library /ˈlaɪbreri/）
    """
    split_er = []
    for i, p in enumerate(phones):
        if p == "ER0" and i + 1 < len(phones) and phones[i + 1][:2] in ARPABET_VOWELS:
            split_er += ["AH0", "R"]
        else:
            split_er.append(p)
    phones = split_er
    vowels = [i for i, p in enumerate(phones) if p[:2] in ARPABET_VOWELS]
    if not vowels:
        return ""
    starts = [0]
    for a, b in zip(vowels, vowels[1:]):
        cluster = phones[a + 1:b]
        split = next(k for k in range(len(cluster) + 1) if k == len(cluster) or tuple(cluster[k:]) in ONSETS)
        starts.append(a + 1 + split)
    stresses = [phones[i][2:] or "0" for i in vowels]
    primary = max((i for i, s in enumerate(stresses) if s == "1"), default=None)
    out = []
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(phones)
        mark = ""
        if len(vowels) > 1 and primary is not None:
            if n == primary:
                mark = "ˈ"
            elif n < primary - 1 and stresses[n] in "12":
                mark = "ˌ"
        sounds = []
        for p in phones[start:end]:
            base, stress = (p[:2], p[2:]) if p[:2] in ARPABET_VOWELS else (p, "")
            if base in ARPABET_VOWELS:
                unstressed = stress == "0" or (stress == "2" and base == "IY" and p is phones[-1])
                sounds.append(ARPABET_UNSTRESSED.get(base, ARPABET_VOWELS[base]) if unstressed else ARPABET_VOWELS[base])
            else:
                sounds.append(ARPABET_CONSONANTS[base])
        out.append(mark + "".join(sounds))
    return "/" + "".join(out) + "/"


# 英式拼写 -> 美式拼写（CMUdict 只收美式拼写）：(英式, 美式)
US_SPELLINGS = [
    ("our", "or"), ("ise", "ize"), ("isa", "iza"), ("yse", "yze"), ("tre", "ter"), ("bre", "ber"),
    ("lment", "llment"), ("lled", "led"), ("lling", "ling"), ("ller", "ler"), ("gramme", "gram"), ("ogue", "og"), ("ae", "e"), ("oe", "e"), ("ence", "ense"),
]
ARPABET_SIBILANTS = ("S", "Z", "SH", "ZH", "CH", "JH")
ARPABET_VOICELESS = ("P", "T", "K", "F", "TH", "S", "SH", "CH")


class UsPhoneticIndex:
    """
    查询美式音标：人工补充表 → CMUdict → 推导（英美拼写差异、词尾变化，人工词表里的词还会尝试拆成合成词）。
    合成词拆分容易出错（compaction 会被拆成 comp + action），所以只用于人工整理、会逐个检查的词表。
    """

    def __init__(self, cmudict_path: Path, overrides):
        self.overrides = overrides
        self.cmu = {}  # 小写单词 -> ARPAbet 音素列表（多个读音只取第一个）
        self.derived = 0
        for line in cmudict_path.read_text(encoding="utf-8").splitlines():
            line = line.split("#")[0].strip()
            if line:
                word, *phones = line.split()
                if "(" not in word:  # word(2) 是第二种读音
                    self.cmu.setdefault(word, phones)

    def lookup(self, word: str, compounds: bool = False) -> str:
        w = word.lower()
        if w in self.overrides:
            return self.overrides[w]
        if re.search(r"[- ]", w) and w not in self.cmu:
            parts = [p for p in re.split(r"[- ]", w) if p]
            found = [self.lookup(p, compounds) for p in parts]
            return "/" + " ".join(p.strip("/") for p in found) + "/" if all(found) else ""
        phones = self.cmu.get(w)
        if not phones:
            phones = self._derive(w, compounds)
            self.derived += bool(phones)
        return arpabet_to_ipa(phones) if phones else ""

    def _derive(self, w: str, compounds: bool):
        # 1. 英式拼写：colour -> color、analyse -> analyze、litre -> liter
        for gb, us in US_SPELLINGS:
            if gb in w:
                found = self.cmu.get(w.replace(gb, us))
                if found:
                    return found
        # 2. 词尾变化：(后缀, 可能的词根, 后缀读音)
        doubled = w[:-4] if len(w) > 5 and w[-4] == w[-5] else None  # planning -> plan
        rules = [
            ("ily", [w[:-3] + "y"], ["L", "IY0"]),
            ("ly", [w[:-2], w[:-1]], ["L", "IY0"]),  # dully -> dull + y
            ("iness", [w[:-5] + "y"], ["N", "AH0", "S"]),
            ("ness", [w[:-4]], ["N", "AH0", "S"]),
            ("less", [w[:-4]], ["L", "AH0", "S"]),
            ("ment", [w[:-4]], ["M", "AH0", "N", "T"]),
            ("wards", [w[:-5] + "ward"], ["Z"]),
            ("ing", [w[:-3] + "e", w[:-3], doubled], ["IH0", "NG"]),
            ("ed", [w[:-1], w[:-2], w[:-3] if len(w) > 4 and w[-3] == w[-4] else None], None),
            ("er", [w[:-1], w[:-2]], ["ER0"]),
            ("s", [w[:-1]], None),
            ("es", [w[:-2]], None),
        ]
        for suffix, stems, sound in rules:
            # leer、gazetteer 不是 -er 结尾的派生词；stasis、campus 不是复数
            if not w.endswith(suffix) or (suffix == "er" and w.endswith("eer")) or (suffix == "s" and w.endswith(("is", "us", "ss"))):
                continue
            for stem in stems:
                # 词根太短容易匹配到无关的词（biped 不是 bip + ed），双写辅音的词根除外（fogged -> fog）
                base = self.cmu.get(stem) if stem and (len(stem) >= 4 or w[len(stem)] == stem[-1]) else None
                if base:
                    if suffix == "ly" and base[-1] == "L":
                        return base + ["IY0"]  # dully、proverbially：词根已经以 /l/ 结尾
                    if sound is None:
                        last = base[-1]
                        if suffix == "ed":
                            sound = ["IH0", "D"] if last in ("T", "D") else ["T" if last in ARPABET_VOICELESS else "D"]
                        else:
                            sound = ["IH0", "Z"] if last in ARPABET_SIBILANTS else ["S" if last in ARPABET_VOICELESS else "Z"]
                    return base + sound
        # 3. 不带连字符的合成词：toolkit = tool + kit
        if not compounds:
            return None
        for i in range(3, len(w) - 2):
            first, second = self.cmu.get(w[:i]), self.cmu.get(w[i:])
            if first and second:
                # 合成词的主重音在第一部分，第二部分的主重音降为次重音
                return first + [p.replace("1", "2") for p in second]
        return None


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


def build_entry(row, phonetics: PhoneticIndex, us_phonetics: UsPhoneticIndex):
    parsed = parse_translation(row["translation"])
    if not parsed:
        return None
    pos, senses = parsed[0]
    word = row["word"].strip()
    if word.lower() in EXCLUDED_WORDS:
        return None
    entry = {"word": WORD_FIXES.get(word, word)}
    phonetic = phonetics.lookup(entry["word"])
    if phonetic:
        entry["phonetic"] = phonetic
    phonetic_us = us_phonetics.lookup(entry["word"])
    if phonetic_us:
        entry["phonetic_us"] = phonetic_us
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
    if len(args) < 2:
        sys.exit(__doc__)
    src = Path(args[0])
    us_phonetics = UsPhoneticIndex(Path(args[1]), load_overrides(US_OVERRIDES_TSV))
    out_dir = Path(args[2]) if len(args) > 2 else Path(__file__).resolve().parent.parent / "wordbooks"
    out_dir.mkdir(parents=True, exist_ok=True)

    curated = {name: load_curated_words(config["tsv"]) for name, config in CURATED_BOOKS.items()}
    curated_words = set().union(*curated.values())
    curated_lower = {w.lower() for w in curated_words}
    curated_rows = {}  # 人工词表里的词在 ECDICT 中对应的行，键为原词或小写形式
    phonetics = PhoneticIndex(load_overrides(OVERRIDES_TSV))

    tag_to_book = {tag: name for name, (tag, _) in BOOKS.items()}
    rows = {name: [] for name in BOOKS}
    basic_count = 0
    with src.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            phonetics.add(row)
            if row["tag"] and is_basic(row):
                basic_count += 1
            else:
                for tag in row["tag"].split():
                    if tag in tag_to_book:
                        rows[tag_to_book[tag]].append(row)
            word = row["word"]
            if word in curated_words:
                curated_rows[word] = row
            if word.lower() in curated_lower:
                curated_rows.setdefault(word.lower(), row)

    print(f"已排除 {basic_count} 个基础词（中考词频前 {BASIC_RANK} 名及首字母大写的词）")
    for name, (_, title) in BOOKS.items():
        book_rows = rows[name]
        if sort_mode == "alpha":
            book_rows.sort(key=lambda r: r["word"].lower())
        else:
            book_rows.sort(key=lambda r: (freq_rank(r), r["word"].lower()))
        entries, seen = [], set()
        for row in book_rows:
            entry = build_entry(row, phonetics, us_phonetics)
            if entry and entry["word"].lower() not in seen:
                seen.add(entry["word"].lower())
                entries.append(entry)
        write_book(out_dir / f"{name}.json", title, entries)

    for name, config in CURATED_BOOKS.items():
        build_curated_book(name, config, curated[name], curated_rows, phonetics, us_phonetics, out_dir, sort_mode)
    print(f"英式音标：{len(phonetics.overrides)} 个词使用人工补充表，{phonetics.derived} 个词由词根推导")
    print(f"美式音标：{len(us_phonetics.overrides)} 个词使用人工补充表，{us_phonetics.derived} 个词由拼写差异、词尾变化或合成词推导")


def write_book(path: Path, title: str, entries):
    # 每个单词一行，文件不会太大，也方便查看
    body = ",\n".join("  " + json.dumps(e, ensure_ascii=False) for e in entries)
    path.write_text("[\n" + body + "\n]\n", encoding="utf-8", newline="\n")
    print(f"{title:<12} {len(entries):>5} 词 -> {path}")


# ---------------------------------------------------------------------------
# 人工整理的词表：scripts/*_words.tsv 提供释义，ECDICT 补充音标和通用释义
# ---------------------------------------------------------------------------

SCRIPTS_DIR = Path(__file__).resolve().parent
CURATED_BOOKS = {
    # 输出文件名: 配置
    #   tsv:   词表文件
    #   title: 显示名称
    #   label: 完整释义第一行的标签，如【编程】
    #   order: "freq" 按词频排序 / "file" 按词表中的顺序
    #   general: 是否在完整释义里附上 ECDICT 的通用释义
    "programmer": {"tsv": SCRIPTS_DIR / "programmer_words.tsv", "title": "程序员词汇", "label": "编程", "order": "freq", "general": True},
    "business": {"tsv": SCRIPTS_DIR / "business_words.tsv", "title": "商务英语", "label": "商务", "order": "freq", "general": True},
    # 易读错词：音标、常见误读和朗读文本都在词表里，不附加 ECDICT 的通用释义
    "mispronounced": {"tsv": SCRIPTS_DIR / "mispronounced_words.tsv", "title": "程序员易读错词", "label": "读音", "order": "file", "general": False},
}


def load_curated_words(path: Path):
    """
    读取人工词表（Tab 分隔）：单词 词性 释义 [音标] [常见误读] [朗读文本] [美式音标]
    返回 {单词: (词性, 释义, 音标, 常见误读, 朗读文本, 美式音标)}，可选列为空字符串。重复的词只保留第一次出现的。
    """
    words, duplicates = {}, []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) < 3 or not all(parts[:3]):
            sys.exit(f"{path.name} 第 {lineno} 行格式错误（需要 单词<Tab>词性<Tab>释义）：{line}")
        word, pos, meaning, phonetic, note, speak, phonetic_us = (parts + [""] * 7)[:7]
        if word in words:
            duplicates.append(word)
            continue
        words[word] = (pos, meaning, phonetic, note, speak, phonetic_us)
    if duplicates:
        print(f"提示：{path.name} 中有重复的词，已保留第一次出现的释义：{', '.join(duplicates)}")
    return words


def build_curated_book(name, config, words, ecdict_rows, phonetics: PhoneticIndex, us_phonetics: UsPhoneticIndex, out_dir: Path, sort_mode: str):
    label = config["label"]
    entries, missing = [], []
    for order, (word, (pos, meaning, phonetic, note, speak, phonetic_us)) in enumerate(words.items()):
        row = ecdict_rows.get(word) or ecdict_rows.get(word.lower())
        entry = {"word": word}
        phonetic = phonetic or phonetics.lookup(word)
        if phonetic:
            entry["phonetic"] = phonetic
        phonetic_us = phonetic_us or us_phonetics.lookup(word, compounds=True)
        if phonetic_us:
            entry["phonetic_us"] = phonetic_us
        entry["pos"] = pos
        entry["meaning"] = meaning
        if speak:
            entry["speak"] = speak
        detail = [f"【{label}】{pos} {meaning}"]
        if note:
            detail.append(f"⚠ 常见误读：{note}")
        if config["general"]:
            # 专业词库：附上 ECDICT 的通用释义，方便对照
            if row:
                detail += [f"{p} {'；'.join(s)}" if p else "；".join(s) for p, s in parse_translation(row["translation"])]
            else:
                missing.append(word)
        entry["detail"] = "\n".join(detail)
        if config["order"] == "file":
            key = (order, "")
        elif sort_mode == "alpha":
            key = (0, word.lower())
        else:
            key = (freq_rank(row) if row else 10**9, word.lower())
        entries.append((key, entry))

    entries.sort(key=lambda e: e[0])
    write_book(out_dir / f"{name}.json", config["title"], [e for _, e in entries])
    if missing:
        print(f"提示：ECDICT 中没有以下词，只使用词表里的释义：{', '.join(missing)}")
    no_phonetic = [e["word"] for _, e in entries if "phonetic" not in e]
    if no_phonetic:
        print(f"提示：以下词没有音标，建议在词表第 4 列补上：{', '.join(no_phonetic)}")
    no_us = [e["word"] for _, e in entries if "phonetic_us" not in e]
    if no_us:
        print(f"提示：以下词没有美式音标，建议在 {US_OVERRIDES_TSV.name} 中补上：{', '.join(no_us)}")


if __name__ == "__main__":
    main()
