#!/usr/bin/env python3
"""
build_data.py — Parse converted MD files into structured JS/JSON data for the VSTEP Study App.
Usage: .venv/bin/python build_data.py
Output: app/data/tests.js, answers.js, tapescripts.js, writing_samples.js
"""

import re
import json
from pathlib import Path

ROOT     = Path(__file__).parent
MD_DIR   = ROOT / "md_output" / "EC INSPRIDE_Đề thi Vstep tham khảo"
KEY_MD   = MD_DIR / "key.md"
APP_DATA = ROOT / "app" / "data"
APP_DATA.mkdir(parents=True, exist_ok=True)


# ── helpers ──────────────────────────────────────────────────────────────────

def clean(text: str) -> str:
    text = re.sub(r'\*+', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)   # strip MD links
    text = re.sub(r'`+', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def extract_options(block: str):  # -> dict | None
    """
    Extract A/B/C/D from any of these formats:
      Inline : A. x  B. y  C. z  D. w
      Two-line: A. x  B. y\nC. z  D. w
      Table  : | A. x | B. y |\n|---|\n| C. z | D. w |
      No-space: A.text (OCR artifact — no space after dot)
      No-dot  : B text (OCR artifact — missing dot)
    """
    opts: dict[str, str] = {}

    # 1) table cells
    for cell in re.findall(r'\|([^|\n]+)', block):
        cell = cell.strip()
        m = re.match(r'^([A-D])\.\s*(.*)', cell)
        if m and not re.match(r'^[-\s]+$', m.group(2)):
            opts[m.group(1)] = clean(m.group(2))
    if len(opts) == 4:
        return opts

    # 2) Position-based split: find where each option marker is, extract text between them.
    #    Handles OCR artifacts: missing dot (B text), missing space (A.text).
    opts = {}
    markers = []
    for key in 'ABCD':
        # Try with dot first (most reliable), then without dot (space required)
        m = re.search(rf'(?<!\w){key}\.\s*', block)
        if not m:
            m = re.search(rf'(?<!\w){key}\s+', block)
        if m:
            markers.append((m.start(), key, m.end()))
    markers.sort()
    if len(markers) == 4 and [x[1] for x in markers] == list('ABCD'):
        for i, (_, key, end) in enumerate(markers):
            text_end = markers[i + 1][0] if i + 1 < len(markers) else len(block)
            opts[key] = clean(block[end:text_end])
        if all(opts.values()):
            return opts

    # 3) inline fallback: original strict regex
    opts = {}
    for m in re.finditer(r'\b([A-D])\.\s+((?:(?!\b[A-D]\.\s).)+)', block, re.DOTALL):
        opts[m.group(1)] = clean(m.group(2))
    if len(opts) == 4:
        return opts

    return None


# ── question parser ───────────────────────────────────────────────────────────

def parse_questions(text: str) -> list[dict]:
    """Split text into numbered question blocks and extract Q + options."""
    questions = []
    # split on lines that start with a digit+dot
    blocks = re.split(r'\n(?=\d{1,2}\.\s)', '\n' + text)

    for block in blocks:
        block = block.strip()
        if not block:
            continue
        m = re.match(r'^(\d{1,2})\.\s+(.*)', block, re.DOTALL)
        if not m:
            continue

        q_num  = int(m.group(1))
        q_body = m.group(2).strip()

        # find where options start (A. with optional space after dot handles "A.text" OCR artifacts)
        opt_start = re.search(r'(?:^|\n|\s{2,}|\|)\s*A\.', q_body)
        if opt_start:
            q_text  = q_body[:opt_start.start()].strip()
            opts_tx = q_body[opt_start.start():]
        else:
            q_text  = q_body
            opts_tx = ''

        options = extract_options(opts_tx) if opts_tx else None

        q_type = 'mc'
        if not options:
            if opts_tx:
                print(f"    [Q{q_num}] could not parse options from: {opts_tx[:80]!r}")
            else:
                # No option markers at all → genuine short-answer question
                q_type = 'short'
            options = {'A': '', 'B': '', 'C': '', 'D': ''}

        questions.append({
            'id':      q_num,
            'type':    q_type,
            'text':    clean(q_text),
            'options': options,
        })

    return questions


# ── section parsers ───────────────────────────────────────────────────────────

def parse_listening(text: str) -> list[dict]:
    parts = []
    boundaries = list(re.finditer(r'^PART\s+(\d+)', text, re.MULTILINE | re.IGNORECASE))
    for i, pm in enumerate(boundaries):
        part_num = int(pm.group(1))
        start    = pm.end()
        end      = boundaries[i + 1].start() if i + 1 < len(boundaries) else len(text)
        chunk    = text[start:end]
        qs       = parse_questions(chunk)
        parts.append({'part': part_num, 'questions': qs})
        print(f"    LISTENING Part {part_num}: {len(qs)} questions")
    return parts


def parse_reading(text: str) -> list[dict]:
    passages = []
    pats = list(re.finditer(
        r'PASSAGE\s+(\d+)\s*[–\-]\s*Questions?\s+(\d+)[–\-](\d+)',
        text, re.IGNORECASE
    ))
    for i, pm in enumerate(pats):
        p_num   = int(pm.group(1))
        q_first = int(pm.group(2))
        start   = pm.end()
        end     = pats[i + 1].start() if i + 1 < len(pats) else len(text)
        chunk   = text[start:end].strip()

        # split passage body from questions
        first_q = re.search(rf'^{q_first}\.\s', chunk, re.MULTILINE)
        if first_q:
            body  = chunk[:first_q.start()].strip()
            q_txt = chunk[first_q.start():]
        else:
            body  = chunk
            q_txt = ''

        qs = parse_questions(q_txt) if q_txt else []
        passages.append({'id': p_num, 'text': body, 'questions': qs})
        print(f"    READING Passage {p_num}: {len(qs)} questions")
    return passages


def parse_writing(text: str) -> dict:
    tasks = {}
    task_matches = list(re.finditer(r'^TASK\s+(\d+)', text, re.MULTILINE | re.IGNORECASE))
    for i, tm in enumerate(task_matches):
        task_num = int(tm.group(1))
        start    = tm.end()
        end      = task_matches[i + 1].start() if i + 1 < len(task_matches) else len(text)
        chunk    = text[start:end].strip()
        bullets  = re.findall(r'[•·]\s*(.+)', chunk)
        # prompt = everything before first bullet
        b_pos   = chunk.find('•')
        prompt  = chunk[:b_pos].strip() if b_pos != -1 else chunk
        tasks[f'task{task_num}'] = {
            'prompt':  clean(prompt),
            'bullets': [clean(b) for b in bullets],
        }
    return tasks


def parse_speaking(text: str) -> dict:
    parts = {}
    pms = list(re.finditer(r'^PART\s+(\d+)\s*:\s*(.+)', text, re.MULTILINE | re.IGNORECASE))
    for i, pm in enumerate(pms):
        part_num  = int(pm.group(1))
        part_name = pm.group(2).strip()
        start     = pm.end()
        end       = pms[i + 1].start() if i + 1 < len(pms) else len(text)
        chunk     = text[start:end].strip()
        questions = re.findall(r'^\d+\.\s+(.+)', chunk, re.MULTILINE)
        lines     = [l.strip() for l in chunk.splitlines() if l.strip()]
        topic     = lines[0] if lines else ''
        parts[f'part{part_num}'] = {
            'title':     clean(part_name),
            'topic':     clean(topic),
            'questions': [clean(q) for q in questions],
        }
    return parts


# ── test MD parser ────────────────────────────────────────────────────────────

def parse_test_md(md_path: Path, test_num: int) -> dict:
    text = md_path.read_text(encoding='utf-8')

    # split into major A/B/C/D sections
    sec_pat = re.compile(
        r'^[A-D]\s*:\s*(LISTENING|READING|WRITING|SPEAKING)',
        re.MULTILINE | re.IGNORECASE
    )
    sms    = list(sec_pat.finditer(text))
    sections: dict[str, str] = {}
    for i, sm in enumerate(sms):
        name  = sm.group(1).upper()
        start = sm.end()
        end   = sms[i + 1].start() if i + 1 < len(sms) else len(text)
        sections[name] = text[start:end]

    print(f"  Test {test_num}: sections = {list(sections.keys())}")

    result: dict = {'id': test_num, 'hasAudio': test_num <= 5}

    if 'LISTENING' in sections:
        result['listening'] = {'parts': parse_listening(sections['LISTENING'])}
    if 'READING' in sections:
        result['reading'] = {'passages': parse_reading(sections['READING'])}
    if 'WRITING' in sections:
        result['writing'] = parse_writing(sections['WRITING'])
    if 'SPEAKING' in sections:
        result['speaking'] = parse_speaking(sections['SPEAKING'])

    return result


# ── key.md parsers ────────────────────────────────────────────────────────────

def parse_answer_keys(key_text: str) -> dict:
    answers: dict = {}
    km = re.search(r'\*\*KEY\*\*', key_text)
    if not km:
        print("WARNING: KEY section not found")
        return answers

    key_section  = key_text[km.end():]
    test_chunks  = re.split(r'\*\*TEST\s+(\d+)\*\*', key_section)

    for i in range(1, len(test_chunks) - 1, 2):
        t   = int(test_chunks[i])
        txt = test_chunks[i + 1]
        answers[t] = {}

        lm = re.search(r'\*\*LISTENING\*\*', txt)
        rm = re.search(r'\*\*REA\w*\*\*', txt, re.IGNORECASE)
        wm = re.search(r'\*\*WRITING\*\*', txt)

        if lm:
            l_end   = rm.start() if rm else len(txt)
            l_block = txt[lm.end():l_end]
            answers[t]['listening'] = {
                int(m.group(1)): m.group(2)
                for m in re.finditer(r'\*\*(\d+)([A-D])\*\*', l_block)
            }

        if rm:
            r_end   = wm.start() if wm else len(txt)
            r_block = txt[rm.end():r_end]
            answers[t]['reading'] = {
                int(m.group(1)): m.group(2)
                for m in re.finditer(r'\*\*(\d+)([A-D])\*\*', r_block)
            }

        print(f"  Test {t}: L={len(answers[t].get('listening',{}))} R={len(answers[t].get('reading',{}))}")

    return answers


def parse_tapescripts(key_text: str) -> dict:
    tapescripts: dict = {}
    ts_m = re.search(r'\*\*TAPESCRIPTS\*\*', key_text)
    key_m = re.search(r'\*\*KEY\*\*', key_text)
    if not ts_m:
        return tapescripts

    section = key_text[ts_m.end():(key_m.start() if key_m else len(key_text))]
    chunks  = re.split(r'\*\*TEST\s+(\d+)\*\*', section)

    for i in range(1, len(chunks) - 1, 2):
        t    = int(chunks[i])
        txt  = chunks[i + 1]
        tapescripts[t] = {}
        parts = re.split(r'\*\*PART\s+(\d+)\s*:?\s*\*\*', txt)
        for j in range(1, len(parts) - 1, 2):
            p_num = int(parts[j])
            tapescripts[t][f'part{p_num}'] = parts[j + 1].strip()

    return tapescripts


def parse_speaking_samples(key_text: str) -> dict:
    """
    Parse speaking model answers from the KEY section of key.md.
    Returns { testNum: { part1: [{q, a, topic}], part2: {prompt, answer}, part3: {topic, answer} } }
    """
    samples: dict = {}
    km = re.search(r'\*\*KEY\*\*', key_text)
    if not km:
        return samples

    section = key_text[km.end():]
    chunks  = re.split(r'\*\*TEST\s+(\d+)\*\*', section)

    for i in range(1, len(chunks) - 1, 2):
        t   = int(chunks[i])
        txt = chunks[i + 1]

        sm = re.search(r'\*\*SPEAKING\*\*', txt)
        if not sm:
            samples[t] = {}
            continue

        sp_txt = txt[sm.end():]
        # cut off at next major section or end
        next_test = re.search(r'\n\*\*TEST\s+\d+\*\*', sp_txt)
        if next_test:
            sp_txt = sp_txt[:next_test.start()]

        result: dict = {}

        # split into PART blocks
        part_splits = re.split(r'\*\*PART\s+(?:I{1,3}|\d+)\s*[:\s]\s*([A-Z][^\*\n]+)\*\*', sp_txt)
        # part_splits[0] = preamble, then alternating [part_name, content] pairs
        for j in range(1, len(part_splits) - 1, 2):
            part_name = part_splits[j].strip().upper()
            content   = part_splits[j + 1].strip()

            if 'SOCIAL' in part_name or part_name == 'PART 1':
                # Part 1: Q&A pairs under topic headers
                qa_list = []
                current_topic = ''
                lines = content.splitlines()
                k = 0
                while k < len(lines):
                    line = lines[k].strip()
                    # topic header: bold/italic "Let's talk about..." (curly or straight apostrophe)
                    if 'talk about' in line.lower():
                        current_topic = re.sub(r'[\*_]+', '', line).strip()
                        k += 1
                        continue
                    # question: line containing ? (may have trailing parentheticals like "(Which?)")
                    q_clean = re.sub(r'^\d+\.\s*', '', line).strip()
                    if '?' in q_clean and len(q_clean) > 5:
                        # answer is next non-empty line
                        answer = ''
                        kk = k + 1
                        while kk < len(lines):
                            ans_line = lines[kk].strip()
                            if ans_line:
                                answer = re.sub(r'[\*_]+', '', ans_line).strip()
                                break
                            kk += 1
                        qa_list.append({'topic': current_topic, 'q': q_clean, 'a': answer})
                        k = kk + 1
                        continue
                    k += 1
                result['part1'] = qa_list

            elif 'SOLUTION' in part_name:
                # Part 2: first non-header line = prompt, bullet = answer
                lines = [l.strip() for l in content.splitlines() if l.strip()]
                prompt = ''
                answer = ''
                for ln in lines:
                    clean_ln = re.sub(r'[\*_]+', '', ln).strip()
                    if ln.startswith('*') or ln.startswith('•'):
                        answer = re.sub(r'^[*•]\s*', '', clean_ln).strip()
                        break
                    if not prompt and clean_ln:
                        prompt = clean_ln
                result['part2'] = {'prompt': prompt, 'answer': answer}

            elif 'TOPIC' in part_name:
                # Part 3: topic line, optional "You should say" sub-bullets, then paragraph answer
                lines = [l.strip() for l in content.splitlines() if l.strip()]
                topic = ''
                sub_bullets: list[str] = []
                answer_lines: list[str] = []
                state = 'topic'
                for ln in lines:
                    clean_ln = re.sub(r'[\*_]+', '', ln).strip()
                    if state == 'topic' and clean_ln:
                        topic = clean_ln
                        state = 'body'
                        continue
                    if state == 'body':
                        # numbered sub-bullets under "You should say"
                        if re.match(r'^\d+\.', ln):
                            sub_bullets.append(re.sub(r'^\d+\.\s*', '', clean_ln))
                        elif clean_ln:
                            answer_lines.append(clean_ln)
                result['part3'] = {
                    'topic':   topic,
                    'bullets': sub_bullets,
                    'answer':  ' '.join(answer_lines),
                }

        samples[t] = result
        print(f"  Speaking samples Test {t}: parts={list(result.keys())}")

    return samples


def parse_writing_samples(key_text: str) -> dict:
    samples: dict = {}
    km = re.search(r'\*\*KEY\*\*', key_text)
    if not km:
        return samples

    section = key_text[km.end():]
    chunks  = re.split(r'\*\*TEST\s+(\d+)\*\*', section)

    for i in range(1, len(chunks) - 1, 2):
        t   = int(chunks[i])
        txt = chunks[i + 1]
        samples[t] = {'task1': {}, 'task2': {}}

        wm = re.search(r'\*\*WRITING\*\*', txt)
        sm = re.search(r'\*\*SPEAKING\*\*', txt)
        if not wm:
            continue

        w_txt = txt[wm.end():(sm.start() if sm else len(txt))]
        task_parts = re.split(r'\*\*TASK\s+(\d+)\*\*', w_txt)

        for j in range(1, len(task_parts) - 1, 2):
            task_num = int(task_parts[j])
            task_txt = task_parts[j + 1]
            key_name = f'task{task_num}'
            level_data: dict = {}

            for level in ['C1', 'B2', 'B1']:
                lm = re.search(rf'\*\*{level}\*\*', task_txt)
                if lm:
                    after = task_txt[lm.end():]
                    # content is inside a markdown table cell
                    cell = re.search(r'\|\s*(.*?)\s*\|', after, re.DOTALL)
                    if cell:
                        level_data[level] = clean(cell.group(1))

            samples[t][key_name] = level_data

    return samples


# ── Priority 1: 30 Speaking Practice Tests ───────────────────────────────────

SPEAKING_30_MD = ROOT / "md_output" / "VSTEP - 9-4-2025" / "30 practice tests for vstep speaking- main content_0001.md"

def parse_speaking_tests(path: Path) -> list[dict]:
    text = path.read_text(encoding='utf-8')
    tests_out = []

    # Normalise known OCR artifacts before splitting
    text = re.sub(r'SPEAKING TEST\s+1ó', 'SPEAKING TEST 16', text)  # ó → 6
    text = re.sub(r'(SPEAKING TEST\s+1)\s*\n', r'SPEAKING TEST 17\n', text)  # lone "1" → 17

    chunks = re.split(r'SPEAKING TEST\s+(\d+)', text)
    for i in range(1, len(chunks) - 1, 2):
        num  = int(chunks[i])
        body = chunks[i + 1]

        result: dict = {'num': num}

        # ── Part I: Social Interaction ──────────────────────────────────────
        m1 = re.search(r'PART\s+I[:\s].*?(?=PART\s+II)', body, re.DOTALL | re.IGNORECASE)
        if m1:
            p1 = m1.group(0)
            groups = []
            topic_parts = re.split(r"(?:Let['']?s|Let’s)\s+talk\s+about\s+(.+?)\.?$", p1, flags=re.MULTILINE | re.IGNORECASE)
            cur_topic = ''
            for j in range(len(topic_parts)):
                part = topic_parts[j].strip()
                if j % 2 == 1:
                    cur_topic = part.rstrip('.')
                else:
                    qs = [re.sub(r'^[-—•]\s*', '', l.strip()) for l in part.splitlines()
                          if l.strip() and re.match(r'^[-—•]', l.strip())]
                    if qs:
                        groups.append({'topic': cur_topic, 'questions': qs})
            result['part1'] = groups

        # ── Part II: Solution Discussion ────────────────────────────────────
        m2 = re.search(r'PART\s+II[:\s].*?(Situation\s*[:：].*?)(?=PART\s+III|30 practice|---)', body, re.DOTALL | re.IGNORECASE)
        if m2:
            sit = re.sub(r'\s+', ' ', m2.group(1)).strip()
            result['part2'] = sit

        # ── Part III: Topic Development ─────────────────────────────────────
        m3_header = re.search(r'PART\s+III[:\s][^\n]*\n', body, re.IGNORECASE)
        if m3_header:
            p3_body = body[m3_header.end():]
            # "Topic:" is on its own line, distinct from the header "TOPIC DEVELOPMENT"
            top_m = re.search(r'^Topic\s*[:：]\s*(.+?)$', p3_body, re.MULTILINE | re.IGNORECASE)
            topic = top_m.group(1).strip().rstrip('.') if top_m else ''
            rest  = p3_body[top_m.end():] if top_m else p3_body
            followups = [re.sub(r'^[-—•]\s*', '', l.strip()) for l in rest.splitlines()
                         if l.strip() and re.match(r'^[-—•]', l.strip()) and '?' in l]
            result['part3'] = {'topic': topic, 'followups': followups}

        tests_out.append(result)
        print(f"    Speaking Test {num}: p1={len(result.get('part1',[]))} groups, p3={result.get('part3',{}).get('topic','?')[:40]}")

    return tests_out


# ── Priority 2: Speaking Topic Model Answers ──────────────────────────────────

SPEAKING_TOPIC_MD = ROOT / "md_output" / "VSTEP - 9-4-2025" / "speaking-soạn 2.docx.md"

def parse_speaking_topic_answers(path: Path) -> dict:
    text = path.read_text(encoding='utf-8')
    result: dict = {}

    # Topics are ALL-CAPS lines (with possible spaces), not starting with common words
    topic_pat = re.compile(r'^([A-Z][A-Z\s]{3,})$', re.MULTILINE)
    boundaries = list(topic_pat.finditer(text))

    for i, bm in enumerate(boundaries):
        topic = bm.group(1).strip()
        # Skip page headers / generic section markers and malformed multi-word topics
        if topic in {'SPEAKING PART 1', 'SPEAKING PART 2', 'SPEAKING PART 3', 'PART 1', 'PART 2', 'PART 3'}:
            continue
        # Skip topics that look like sentence fragments (contain many small words or >30 chars per word)
        words = topic.split()
        if len(words) > 5 or any(len(w) > 20 for w in words):
            continue
        start = bm.end()
        end   = boundaries[i + 1].start() if i + 1 < len(boundaries) else len(text)
        block = text[start:end].strip()

        # Extract Q&A pairs: question ends with ?, answer is next non-empty paragraph
        qas = []
        paras = [p.strip() for p in re.split(r'\n\s*\n', block) if p.strip()]
        j = 0
        while j < len(paras):
            p = paras[j]
            clean = re.sub(r'[\*_]+', '', p).strip()
            if clean.endswith('?') and len(clean) > 5:
                answer = paras[j + 1].strip() if j + 1 < len(paras) else ''
                qas.append({'q': clean, 'a': answer})
                j += 2
            else:
                j += 1

        if qas:
            result[topic] = qas
            print(f"    Speaking topic '{topic}': {len(qas)} Q&As")

    return result


# ── Priority 3: 30 Essay Writing Samples ─────────────────────────────────────

ESSAYS_30_MD = ROOT / "md_output" / "VSTEP - 9-4-2025" / "30 BÀI VIẾT LUẬN MẪU B1B2 - VSTEP_edited.md"

# Topics from table of contents (in order of appearance)
ESSAY_TOPICS = [
    "Online learning", "Studying abroad", "Being famous", "Homeschooling",
    "Extracurricular activities", "Advertising", "Public transport", "Multitasking",
    "Public spaces", "Learning foreign languages", "University attendance", "Media",
    "Smoking", "University education vs vocational training",
    "Job satisfaction vs high salary", "Buying products abroad", "Doing housework",
    "Video games", "English as the international language", "Deciding school subjects",
    "Single life", "Technology in education", "Stress", "Internet addiction",
    "Obesity", "International travel", "Youth crimes", "Delaying childbirth",
    "Soft skills", "Brain drain",
]

ESSAY_TYPES = [
    *["Advantage-Disadvantage"] * 9,
    *["Opinion"] * 8,
    *["Discussion"] * 3,
    *["Problem-Solution"] * 10,
]

VN_CHARS = set('àáâãèéêìíòóôõùúýăđơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỷỹỵ'
               'ÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝĂĐƠƯẠẢẤẦẨẪẬẮẰẲẴẶẸẺẼẾỀỂỄỆỈỊỌỎỐỒỔỖỘỚỜỞỠỢỤỦỨỪỬỮỰỲỶỸỴ')

def is_vietnamese(s: str) -> bool:
    return sum(1 for c in s if c in VN_CHARS) / max(len(s), 1) > 0.04

def extract_english_essay(text: str, marker: str) -> str:
    """Find B1 or B2 essay block: from the marker to the next (NNN words) line."""
    # Find the level header line (Bl = OCR'd B1, or B2)
    pat = re.compile(rf'^{re.escape(marker)}\s*$', re.MULTILINE)
    m = pat.search(text)
    if not m:
        return ''
    chunk = text[m.end():]
    # Cut at word count marker
    wc = re.search(r'\(\d+ words\)', chunk)
    if wc:
        chunk = chunk[:wc.start()]
    # Keep only English paragraphs
    paras = [p.strip() for p in chunk.split('\n\n') if p.strip()]
    english = [p for p in paras if not is_vietnamese(p) and len(p) > 50]
    return '\n\n'.join(english).strip()

def parse_extra_essays(path: Path) -> list[dict]:
    text = path.read_text(encoding='utf-8')
    essays_out = []

    # Split by "You should spend about 40 minutes"
    prompt_pat = re.compile(r'You should spend about 40 minutes on this task\.?\s*[(\s]?', re.IGNORECASE)
    splits = list(prompt_pat.finditer(text))

    for idx, pm in enumerate(splits):
        end   = splits[idx + 1].start() if idx + 1 < len(splits) else len(text)
        chunk = text[pm.start():end]

        # Extract English prompt (up to first Vietnamese paragraph or word limit line)
        prompt_end = re.search(
            r'(?:Your response will be evaluated|You should write at least \d+ words)',
            chunk, re.IGNORECASE
        )
        raw_prompt = chunk[:prompt_end.end()].strip() if prompt_end else chunk[:400].strip()
        # Keep only lines that are English
        prompt_lines = [l for l in raw_prompt.splitlines() if l.strip() and not is_vietnamese(l)]
        prompt = ' '.join(prompt_lines).strip()

        # B1 essay (Bl is OCR artifact for B1)
        b1 = extract_english_essay(chunk, 'Bl') or extract_english_essay(chunk, 'B1')
        b2 = extract_english_essay(chunk, 'B2')

        topic = ESSAY_TOPICS[idx] if idx < len(ESSAY_TOPICS) else f'Essay {idx+1}'
        etype = ESSAY_TYPES[idx] if idx < len(ESSAY_TYPES) else 'Essay'

        essays_out.append({
            'num': idx + 1,
            'topic': topic,
            'type': etype,
            'prompt': prompt,
            'B1': b1,
            'B2': b2,
        })
        b1w = len(b1.split()) if b1 else 0
        b2w = len(b2.split()) if b2 else 0
        print(f"    Essay {idx+1}: {topic[:30]} | B1={b1w}w B2={b2w}w")

    return essays_out


# ── Priority 4: VSTEP Collection — 5 extra Mock Tests ────────────────────────

COLLECTION_MD = ROOT / "md_output" / "VSTEP collection 20 Mock Tests - Full Key.md"

def parse_collection_answers(text: str) -> dict:
    """Parse the answer key section for all 5 collection tests."""
    answers: dict = {}
    km = re.search(r'ANSWER\s+KEY[S,\s]*\n', text, re.IGNORECASE)
    if not km:
        return answers

    key_section = text[km.end():]
    # Split by "ANSWER KEY- LISTENING TEST N"
    test_blocks = re.split(r'ANSWER KEY[-–]\s*LISTENING TEST\s+(\d+)', key_section)

    for i in range(1, len(test_blocks) - 1, 2):
        t = int(test_blocks[i])
        block = test_blocks[i + 1]

        answers[t] = {}
        # Listening: extract all "ND" patterns (number + letter A-D)
        l_end = re.search(r'ANSWER KEY[-–].*?READING', block, re.IGNORECASE)
        l_block = block[:l_end.start()] if l_end else block[:2000]
        l_pairs = re.findall(r'(\d+)[.\s\[|]*([A-D])', l_block)
        if l_pairs:
            answers[t]['listening'] = {int(k): v for k, v in l_pairs}

        # Reading
        r_start = re.search(r'ANSWER KEY[-–].*?READING.*?\n', block, re.IGNORECASE)
        if r_start:
            r_block = block[r_start.end():r_start.end() + 1500]
            r_pairs = re.findall(r'(\d+)[.\s]*([A-D])', r_block)
            if r_pairs:
                answers[t]['reading'] = {int(k): v for k, v in r_pairs}

        print(f"  Collection Test {t}: L={len(answers[t].get('listening',{}))} R={len(answers[t].get('reading',{}))}")

    return answers


def parse_collection_writing(text: str) -> dict:
    """Extract writing model answers for each collection test."""
    writing: dict = {}
    test_blocks = re.split(r'MODEL ANSWER[-–\s]+WRITING TEST\s+(\d+)', text, flags=re.IGNORECASE)
    for i in range(1, len(test_blocks) - 1, 2):
        t = int(test_blocks[i])
        block = test_blocks[i + 1]
        # Split into Task 1 and Task 2
        t2 = re.search(r'\bTask\s+2\b', block, re.IGNORECASE)
        next_sec = re.search(r'SUGGESTED IDEAS|ANSWER KEY|COLLECTION \d', block, re.IGNORECASE)
        t1_text = block[:t2.start()].strip() if t2 else block[:1000].strip()
        t2_text = block[t2.end():(next_sec.start() if next_sec else len(block))].strip() if t2 else ''
        writing[t] = {
            'task1': [l.strip() for l in t1_text.splitlines() if l.strip() and not is_vietnamese(l)],
            'task2': [l.strip() for l in t2_text.splitlines() if l.strip() and not is_vietnamese(l)],
        }
    return writing


def parse_collection_speaking(text: str) -> dict:
    """Extract suggested ideas for speaking for each collection test."""
    speaking: dict = {}
    test_blocks = re.split(r'SUGGESTED IDEAS FOR SPEAKING TEST\s+(\d+)', text, flags=re.IGNORECASE)
    for i in range(1, len(test_blocks) - 1, 2):
        t = int(test_blocks[i])
        block = test_blocks[i + 1]
        next_sec = re.search(r'ANSWER KEY|COLLECTION \d', block, re.IGNORECASE)
        sp_text = block[:next_sec.start()].strip() if next_sec else block.strip()

        parts: dict = {}
        # Part 1: Social Interaction topics
        p1m = re.search(r'Part\s+1.*?Social Interaction', sp_text, re.IGNORECASE | re.DOTALL)
        p2m = re.search(r'Part\s+2.*?Solution Discussion', sp_text, re.IGNORECASE | re.DOTALL)
        p3m = re.search(r'Part\s+3.*?Topic Development', sp_text, re.IGNORECASE | re.DOTALL)

        def get_block(m_start, m_end):
            s = m_start.end() if m_start else 0
            e = m_end.start() if m_end else len(sp_text)
            return sp_text[s:e].strip()

        p1_text = get_block(p1m, p2m)
        p2_text = get_block(p2m, p3m)
        p3_text = get_block(p3m, None)

        # Part 1 topics
        topics_1 = []
        for tm in re.finditer(r"(?:Let[''’]?s\s+talk\s+about\s+)?([^\n]+?)\.", p1_text):
            questions = re.findall(r'[—–-]\s+(.+\?)', sp_text)
            topics_1.append({'topic': tm.group(1).strip(), 'questions': []})
        # Simple: just grab all questions
        p1_questions = re.findall(r'[—–-]\s+(.+\?)', p1_text)
        parts['part1'] = {'questions': p1_questions}

        # Part 2 situation
        sit_m = re.search(r'Situation[:：]\s*(.+?)(?:\n\n|\Z)', p2_text, re.DOTALL)
        parts['part2'] = sit_m.group(1).replace('\n', ' ').strip() if sit_m else p2_text[:300]

        # Part 3 topic
        top_m = re.search(r'Topic[:：]\s*(.+?)$', p3_text, re.MULTILINE)
        followups = re.findall(r'[—–-]\s+(.+\?)', p3_text)
        parts['part3'] = {
            'topic': top_m.group(1).strip() if top_m else '',
            'followups': followups,
        }

        speaking[t] = parts
    return speaking


def parse_collection_tests(text: str, base_num: int = 8):  # -> tuple[dict, dict]
    """
    Parse all 5 collection tests from the big MD file.
    Returns (tests_dict, answers_dict) with keys base_num..base_num+4
    """
    tests_out: dict  = {}
    answers_out: dict = {}

    # Split at collection boundaries (or at PART 1: Questions headers)
    # Use both COLLECTION N and the end-of-reading markers to find test blocks
    end_read_pat  = re.compile(r'THIS IS THE END OF THE READING PAPER', re.IGNORECASE)
    end_listen_pat = re.compile(r'THIS IS THE END OF THE LISTENING PAPER', re.IGNORECASE)
    speaking_pat  = re.compile(r'PHAN 4.*?NÓI|Part 1.*?Social Interaction.*?\(3', re.IGNORECASE | re.DOTALL)

    # Find all 5 test blocks by splitting at end-of-reading markers
    reading_ends = list(end_read_pat.finditer(text))

    for idx, rem in enumerate(reading_ends):
        test_num = base_num + idx
        print(f"\n  Parsing Collection Test {idx+1} → Test {test_num}...")

        # Reading block: from previous end-of-reading (or start) to this one
        r_start = reading_ends[idx - 1].end() if idx > 0 else 0
        r_end   = rem.end()
        r_chunk = text[r_start:r_end]

        # Find listening block end within this chunk
        le = list(end_listen_pat.finditer(r_chunk))
        listen_chunk = r_chunk[:le[0].start()] if le else ''
        read_chunk   = r_chunk[le[0].end():] if le else r_chunk

        # Detect speaking block (after this reading end, before next)
        sp_after = text[rem.end(): reading_ends[idx+1].start() if idx+1 < len(reading_ends) else len(text)]

        # ── Listening ──────────────────────────────────────────────────────
        listen_parts = parse_listening(listen_chunk) if listen_chunk else []

        # ── Reading ────────────────────────────────────────────────────────
        passages = parse_reading(read_chunk) if read_chunk else []

        # ── Writing (from speaking block area that contains Task 1/Task 2) ─
        wm = re.search(r'PHAN 3.*?VIE[T|Ế]|WRITING|Task 1', sp_after, re.IGNORECASE | re.DOTALL)
        writing = {}
        if wm:
            w_chunk = sp_after[wm.start():wm.start()+1500]
            t1m = re.search(r'Task\s+1\s*[:：]?(.*?)(?=Task\s+2|\Z)', w_chunk, re.DOTALL | re.IGNORECASE)
            t2m = re.search(r'Task\s+2\s*[:：]?\s*(.*?)$', w_chunk, re.DOTALL | re.IGNORECASE | re.MULTILINE)
            if t1m:
                t1_lines = [l.strip() for l in t1m.group(1).splitlines() if l.strip() and not is_vietnamese(l)]
                writing['task1'] = {'prompt': ' '.join(t1_lines[:5]), 'bullets': []}
            if t2m:
                t2_lines = [l.strip() for l in t2m.group(1).splitlines() if l.strip() and not is_vietnamese(l)]
                writing['task2'] = {'prompt': ' '.join(t2_lines[:5]), 'bullets': []}

        # ── Speaking ───────────────────────────────────────────────────────
        sp_sections = {}
        sp_m = re.search(r'Part\s+1.*?Social Interaction', sp_after, re.IGNORECASE | re.DOTALL)
        if sp_m:
            sp_text = sp_after[sp_m.start():]
            sp_sections = parse_speaking(sp_text)

        tests_out[test_num] = {
            'id': test_num,
            'hasAudio': False,
            'listening': {'parts': listen_parts} if listen_parts else None,
            'reading':   {'passages': passages}  if passages   else None,
            'writing':   writing                 if writing    else None,
            'speaking':  sp_sections             if sp_sections else None,
        }

        print(f"    L={sum(len(p['questions']) for p in listen_parts)} "
              f"R={sum(len(p['questions']) for p in passages)} "
              f"W={list(writing.keys())} SP={list(sp_sections.keys())}")

    # Parse answer keys
    answers_raw = parse_collection_answers(text)
    for idx, (t, ans) in enumerate(answers_raw.items()):
        answers_out[base_num + idx] = ans

    return tests_out, answers_out


# ── main ──────────────────────────────────────────────────────────────────────

def write_js(filename: str, var_name: str, data: object) -> None:
    path = APP_DATA / filename
    path.write_text(
        f'const {var_name} = {json.dumps(data, ensure_ascii=False, indent=2)};\n',
        encoding='utf-8'
    )
    print(f"  Written → {path}")


def main() -> None:
    print("=" * 60)
    print("Building VSTEP app data\n")

    # 1. Parse 7 test files
    tests: dict = {}
    for n in range(1, 8):
        md_file = MD_DIR / f"Đề {n}" / f"Đề Test {n}.md"
        if md_file.exists():
            print(f"\nParsing Test {n}...")
            tests[n] = parse_test_md(md_file, n)
        else:
            print(f"SKIP (not found): {md_file}")

    # 2. Parse key.md
    print("\nParsing key.md...")
    key_text = KEY_MD.read_text(encoding='utf-8')
    answers          = parse_answer_keys(key_text)
    tapescripts      = parse_tapescripts(key_text)
    writing_samples  = parse_writing_samples(key_text)
    speaking_samples = parse_speaking_samples(key_text)

    # 3. Priority 1: 30 speaking practice tests
    print("\nPriority 1: Parsing 30 speaking practice tests...")
    if SPEAKING_30_MD.exists():
        speaking_tests = parse_speaking_tests(SPEAKING_30_MD)
    else:
        speaking_tests = []
        print(f"  SKIP (not found): {SPEAKING_30_MD}")

    # 4. Priority 2: Speaking topic model answers
    print("\nPriority 2: Parsing speaking topic answers...")
    if SPEAKING_TOPIC_MD.exists():
        speaking_topic_answers = parse_speaking_topic_answers(SPEAKING_TOPIC_MD)
    else:
        speaking_topic_answers = {}
        print(f"  SKIP (not found): {SPEAKING_TOPIC_MD}")

    # 5. Priority 3: 30 B1/B2 essay writing samples
    print("\nPriority 3: Parsing 30 essay writing samples...")
    if ESSAYS_30_MD.exists():
        extra_essays = parse_extra_essays(ESSAYS_30_MD)
    else:
        extra_essays = []
        print(f"  SKIP (not found): {ESSAYS_30_MD}")

    # 6. Priority 4: VSTEP Collection extra mock tests (8–12)
    print("\nPriority 4: Parsing VSTEP Collection mock tests...")
    if COLLECTION_MD.exists():
        col_text = COLLECTION_MD.read_text(encoding='utf-8')
        col_tests, col_answers = parse_collection_tests(col_text, base_num=8)
        tests.update(col_tests)
        answers.update(col_answers)
    else:
        print(f"  SKIP (not found): {COLLECTION_MD}")

    # 7. Write JS data files
    print("\nWriting data files...")
    write_js('tests.js',                  'TESTS',                  tests)
    write_js('answers.js',                'ANSWERS',                answers)
    write_js('tapescripts.js',            'TAPESCRIPTS',            tapescripts)
    write_js('writing_samples.js',        'WRITING_SAMPLES',        writing_samples)
    write_js('speaking_samples.js',       'SPEAKING_SAMPLES',       speaking_samples)
    write_js('speaking_tests.js',         'SPEAKING_TESTS',         speaking_tests)
    write_js('speaking_topic_answers.js', 'SPEAKING_TOPIC_ANSWERS', speaking_topic_answers)
    write_js('extra_essays.js',           'EXTRA_ESSAYS',           extra_essays)

    print(f"\n{'='*60}")
    print(f"Done.  Tests: {sorted(tests.keys())}  |  Answers: {sorted(answers.keys())}")
    print(f"  Speaking tests: {len(speaking_tests)} | Topics: {len(speaking_topic_answers)} | Essays: {len(extra_essays)}")


if __name__ == '__main__':
    main()
