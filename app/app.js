/* app.js — shared utilities for VSTEP Study App */

const APP = {
  getTestNum() {
    return parseInt(new URLSearchParams(location.search).get('test') || '1');
  },

  getAnswers(testNum) {
    const saved = localStorage.getItem(`vstep_answers_${testNum}`);
    return saved
      ? JSON.parse(saved)
      : { listening: {}, reading: {}, writing: { task1: '', task2: '' } };
  },

  saveAnswers(testNum, answers) {
    localStorage.setItem(`vstep_answers_${testNum}`, JSON.stringify(answers));
  },

  clearAnswers(testNum) {
    localStorage.removeItem(`vstep_answers_${testNum}`);
  },

  calcScore(testNum, answers) {
    const key = ANSWERS[testNum];
    if (!key) return {};
    const result = {};
    for (const section of ['listening', 'reading']) {
      if (!key[section]) continue;
      let correct = 0;
      const total = Object.keys(key[section]).length;
      for (const [qId, correctAns] of Object.entries(key[section])) {
        if (String(answers[section]?.[qId]) === String(correctAns)) correct++;
      }
      result[section] = { correct, total };
    }
    return result;
  },

  scoreClass(correct, total) {
    const pct = correct / total;
    if (pct >= 0.8) return 'good';
    if (pct >= 0.5) return 'ok';
    return 'bad';
  },

  // Flatten test listening into [{partNum, partIndex, q}...]
  flatListening(test) {
    const out = [];
    if (!test?.listening?.parts) return out;
    test.listening.parts.forEach((part, pi) => {
      part.questions.forEach(q => out.push({ partNum: part.part, partIndex: pi, q }));
    });
    return out;
  },

  // Flatten test reading into [{passageIndex, passage, q}...]
  flatReading(test) {
    const out = [];
    if (!test?.reading?.passages) return out;
    test.reading.passages.forEach((p, pi) => {
      p.questions.forEach(q => out.push({ passageIndex: pi, passage: p, q }));
    });
    return out;
  },

  audioSrc(testNum, partNum) {
    return `../Audio/T${testNum}-PART${partNum}.mp3`;
  },

  formatTime(seconds) {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  },

  countWords(text) {
    return text.trim().split(/\s+/).filter(Boolean).length;
  },

  // Render options (A/B/C/D) as radio labels
  renderOptions(q, savedAnswer, reviewMode = false, correctAnswer = null) {
    return ['A', 'B', 'C', 'D'].map(key => {
      const text = q.options[key] || '';
      if (!text && !reviewMode) return '';
      let cls = '';
      if (reviewMode) {
        if (key === correctAnswer) cls = 'correct-ans';
        if (key === savedAnswer && key !== correctAnswer) cls = 'wrong';
        if (key === savedAnswer && key === correctAnswer) cls = 'correct';
      } else {
        if (key === savedAnswer) cls = 'selected';
      }
      const checked = key === savedAnswer ? 'checked' : '';
      const disabled = reviewMode ? 'disabled' : '';
      return `
        <label class="option-label ${cls}" data-key="${key}">
          <input type="radio" name="q${q.id}" value="${key}" ${checked} ${disabled}>
          <span class="opt-key">${key}.</span>
          <span>${text}</span>
        </label>`;
    }).join('');
  },
};
