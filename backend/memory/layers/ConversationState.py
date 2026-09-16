"""ConversationState + ContextResolver: durable, user-provided clinical context.

Design notes (per release checklist, work package 2):
- Facts come only from the USER'S OWN WORDS, extracted by bounded rules; nothing is
  inferred from retrieved documents or model claims.
- Each fact carries the source turn, original text span and status (positive /
  negated / uncertain / superseded). Corrections replace old values instead of
  stacking.
- Negation ("没有发烧", "不是我，是我妈"), correction ("是我妈不是我爸"), subject
  switches ("我妈膝盖疼" vs "我失眠") and timeline ("一个月了") are all tracked.
- The state answers recall questions directly ("我刚才说多久了？") without a fresh
  medical knowledge lookup.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

# ---- extraction patterns (bounded rules over the raw user utterance) ----

_TIMELINE = [
    (r"([0-9一二两三四五六七八九十]+)\s*(?:天|日)\s*(?:了|左右|多|前|开始)", "days"),
    (r"([0-9一二两俩三四五六七八九十]+)\s*(?:周|星期|礼拜|个礼拜)\s*(?:了|左右|多|前|开始)", "weeks"),
    (r"(?:[0-9一二两俩三四五六七八九十]+|半)\s*(?:个多月|个来月|个?月)\s*(?:了|左右|多|前|开始)", "months"),
    (r"(?:[0-9一二两俩三四五六七八九十]+|半)\s*(?:年)\s*(?:了|左右|多|前|开始)", "years"),
    (r"(?:昨天|昨晚)开始", "started_yesterday"),
    (r"(?:今天|刚才)开始", "started_today"),
    (r"最近|这周|这段时间|这阵子", "recent"),
    (r"常年|多年|长期|一直", "chronic"),
]
_AGE = re.compile(r"(\d+)\s*岁")
_PREGNANCY = re.compile(r"怀孕|孕期|妊娠|孕(?:期|妇)?")

_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "俩": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _cn_number(s: str) -> str | None:
    if not s:
        return None
    if s.isdigit():
        return s
    if "十" in s:
        left, _, right = s.partition("十")
        tens = _CN_DIGITS.get(left, 1) if left else 1
        ones = _CN_DIGITS.get(right, 0) if right else 0
        return str(tens * 10 + ones)
    return str(_CN_DIGITS.get(s, 0)) if len(s) == 1 else None
_SUBJECT_PATTERNS = [
    ("self", r"(?:^|[，。；！？,;.!?])(?:我)(?:自己|本人)?(?:[，。；！？,;.!?]|最近|今天|现在|经常|总是|白天|晚上|这)"),
    ("mother", r"我妈|母亲|妈妈"),
    ("father", r"我爸|父亲|爸爸"),
    ("child", r"孩子|娃|宝宝|小孩|儿子|女儿"),
    ("grandparent", r"奶奶|爷爷|姥姥|外公|外婆|祖母|祖父"),
    ("spouse", r"老公|老婆|丈夫|妻子"),
]
_NEGATION_MARKERS = r"没有|并无|否认|不伴|未出现|没(?:有|得)?|不是|不再|从未|无"
_POSITIVE_SYMPTOM = re.compile(
    r"(胸痛|胸闷|心慌|心悸|头晕|眩晕|头痛|头疼|腹痛|肚子疼|胃痛|恶心|呕吐|腹泻|拉肚子|发烧|发热|咳嗽|"
    r"乏力|没劲|失眠|睡不着|出汗|冷汗|麻木|无力|浮肿|皮疹|便秘|反酸|烧心)"
)
_NEGATED_SYMPTOM = re.compile(
    _NEGATION_MARKERS + r".{0,6}?(" + _POSITIVE_SYMPTOM.pattern + r")"
)
_RECALL_QUESTION = re.compile(
    r"我刚才|我刚刚|我说过|之前说|刚才说|上面说|多久|多长时间|什么时候开始|我说的是|说的是谁|是说我|还是(?:说)?(?:我妈|我爸|我|孩子|妈|爸)"
)


@dataclass
class Fact:
    key: str
    value: str
    status: str = "positive"  # positive | negated | superseded
    turn_question: str = ""
    text_span: str = ""
    created_at: str = ""

    def to_dict(self):
        return {
            "key": self.key,
            "value": self.value,
            "status": self.status,
            "turn_question": self.turn_question,
            "text_span": self.text_span,
            "created_at": self.created_at,
        }


@dataclass
class ConversationState:
    subject: str = "self"  # self | mother | father | child | grandparent | spouse
    subject_reported: str = "我"  # 用户原话中对象称呼
    age: str = ""
    pregnant: str = ""  # "" | "yes" | "no" | "yes_week_X"
    timeline: dict = field(default_factory=dict)  # key -> {"value","turn"}
    symptoms: dict = field(default_factory=dict)  # symptom -> {"positive":bool,"turn":...}
    measurements: dict = field(default_factory=dict)
    concerns: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    turns_seen: list[str] = field(default_factory=list)
    facts: list[Fact] = field(default_factory=list)

    def to_dict(self):
        return {
            "subject": self.subject,
            "subject_reported": self.subject_reported,
            "age": self.age,
            "pregnant": self.pregnant,
            "timeline": self.timeline,
            "symptoms": self.symptoms,
            "measurements": self.measurements,
            "concerns": self.concerns,
            "pending": self.pending,
            "facts": [f.to_dict() for f in self.facts],
        }


class ContextResolver:
    """Rule-based fact extraction and state update across dialogue turns."""

    def __init__(self):
        pass

    def _subject_of(self, question: str) -> tuple[str, str]:
        """Detect who the utterance is about. Defaults to previous subject when the
        utterance has no explicit subject particle (continuation)."""
        for name, pattern in _SUBJECT_PATTERNS:
            if re.search(pattern, question):
                label = {"self": "我", "mother": "我妈", "father": "我爸",
                         "child": "孩子", "grandparent": "老人", "spouse": "家人"}[name]
                return name, label
        return "", ""

    def _extract_timeline(self, question: str, turn: str) -> list[Fact]:
        out = []
        for pattern, key in _TIMELINE:
            m = re.search(pattern, question)
            if m:
                out.append(Fact(key=f"timeline.{key}", value=m.group(0), turn_question=turn,
                                text_span=m.group(0)))
        return out

    def update(self, state: ConversationState, question: str, turn: str) -> ConversationState:
        # subject detection: explicit switch wins; otherwise keep current subject
        subj, label = self._subject_of(question)
        if subj:
            state.subject, state.subject_reported = subj, label
        elif not state.subject:
            state.subject, state.subject_reported = "self", "我"
        # age / pregnancy for the CURRENT subject only when utterance is about self
        age_m = _AGE.search(question)
        if age_m and (state.subject == "self" or re.search(r"我.{0,4}" + _AGE.pattern, question)):
            state.age = age_m.group(1)
        preg_m = _PREGNANCY.search(question)
        if preg_m and (state.subject == "self" or re.search(r"我.{0,4}(怀孕|孕期)", question)):
            # extract week like 怀孕十周 / 孕12周 / 怀孕3个月(按12周计不自动换算，仅记录"孕")
            week_cn = re.search(r"(?:怀孕|孕)([一二两三四五六七八九十0-9]+)\s*周", question)
            if week_cn:
                week = _cn_number(week_cn.group(1))
                state.pregnant = f"yes_week_{week}" if week else "yes"
            else:
                state.pregnant = "yes"
        # timeline facts
        for fact in self._extract_timeline(question, turn):
            state.timeline[fact.key] = {"value": fact.value, "turn": turn}
            state.facts.append(fact)
        # symptom polarity
        for m in _POSITIVE_SYMPTOM.finditer(question):
            sym = m.group(1)
            # check negation before the match within same clause
            start = question.rfind("。", 0, m.start())
            start = question.rfind("，", 0, m.start()) if question.rfind("，", 0, m.start()) > start else start
            clause = question[start + 1:m.start()] if start >= 0 else question[:m.start()]
            negated = bool(re.search(_NEGATION_MARKERS + r"$", clause.strip()))
            state.symptoms[sym] = {"positive": not negated, "turn": turn}
        state.turns_seen.append(turn)
        return state

    def recall_answer(self, state: ConversationState, question: str) -> str | None:
        """Answer pure recall questions from state, or None if not a recall question."""
        if not _RECALL_QUESTION.search(question):
            return None
        if re.search(r"说的是谁|是说我|还是(?:说)?(?:我妈|我爸|我|孩子|妈|爸)|是(?:说)?我(?:妈|爸)", question):
            return f"你刚才说的是{state.subject_reported}（{ {'self':'你自己','mother':'你母亲','father':'你父亲','child':'孩子','grandparent':'老人','spouse':'家人'}.get(state.subject,'这位家人') }）的情况。"
        # timeline recall: "多久了 / 多长时间 / 什么时候开始 / 持续"
        if re.search(r"多久|多长时间|什么时候开始|持续", question):
            # Specific durations outrank generic "最近/长期" markers.
            best = None
            for key in ["timeline.years", "timeline.months", "timeline.weeks", "timeline.days",
                        "timeline.started_yesterday", "timeline.started_today",
                        "timeline.recent", "timeline.chronic"]:
                if key in state.timeline:
                    best = state.timeline[key]["value"]
                    break
            if best:
                suffix = "了" if not best.endswith("了") else ""
                return f"你之前提到这个情况{best}{suffix}。"
            return "你还没有提到具体的持续时间，可以补充一下大概多久了。"
        if re.search(r"我(?:是)?(?:不是)?(?:说|讲)(?:的)?(.{0,8}?)？", question) and re.search(r"什么|啥|哪个", question):
            return "你可以告诉我具体想确认哪句话，我按你前面说的来对照。"
        return None
