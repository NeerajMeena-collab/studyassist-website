document.addEventListener('DOMContentLoaded', () => {
  const themeButtons = [...document.querySelectorAll('[data-theme-toggle]')];
  const applyTheme = (theme) => {
    document.documentElement.dataset.theme = theme;
    themeButtons.forEach((button) => {
      const dark = theme === 'dark';
      button.textContent = dark ? '☀' : '☾';
      button.setAttribute('aria-label', dark ? 'Switch to light mode' : 'Switch to dark mode');
      button.title = dark ? 'Switch to light mode' : 'Switch to dark mode';
    });
  };
  let initialTheme = document.documentElement.dataset.theme || 'light';
  try { initialTheme = localStorage.getItem('studyassist-theme') || initialTheme; } catch (_error) { /* Storage may be disabled. */ }
  applyTheme(initialTheme);
  themeButtons.forEach((button) => {
    button.addEventListener('click', () => {
      const nextTheme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
      applyTheme(nextTheme);
      try { localStorage.setItem('studyassist-theme', nextTheme); } catch (_error) { /* Theme still applies for this page. */ }
    });
  });

  document.querySelectorAll('[data-dismiss]').forEach((button) => {
    button.addEventListener('click', () => button.closest('.flash')?.remove());
  });

  if (window.matchMedia('(hover: hover) and (pointer: fine)').matches) {
    const glowSurfaces = document.querySelectorAll(
      '.stat-card, .panel, .subject-card, .suggestion-card, .streak-banner, .tip-card, .auth-card, .auth-art, .attendance-calendar-panel, .attendance-subjects, .dashboard-clock'
    );
    glowSurfaces.forEach((surface) => {
      surface.classList.add('pointer-glow-surface');
      surface.addEventListener('pointermove', (event) => {
        const bounds = surface.getBoundingClientRect();
        surface.style.setProperty('--glow-x', `${event.clientX - bounds.left}px`);
        surface.style.setProperty('--glow-y', `${event.clientY - bounds.top}px`);
        surface.classList.add('pointer-glow-active');
      });
      surface.addEventListener('pointerleave', () => surface.classList.remove('pointer-glow-active'));
    });
  }

  const liveTime = document.querySelector('[data-live-time]');
  const liveDate = document.querySelector('[data-live-date]');
  const timeGreeting = document.querySelector('[data-time-greeting]');
  const dashboardHero = document.querySelector('[data-dashboard-hero]');
  const clockHours = document.querySelector('[data-clock-hours]');
  const clockMinutes = document.querySelector('[data-clock-minutes]');
  if (liveTime || liveDate || timeGreeting || dashboardHero) {
    const updateClock = () => {
      const now = new Date();
      const hour = now.getHours();
      if (liveTime) {
        const localTime = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(now);
        liveTime.textContent = localTime;
        liveTime.parentElement?.setAttribute('aria-label', 'Current local time: ' + localTime);
        liveTime.dateTime = now.toISOString();
      }
      if (clockHours) {
        clockHours.textContent = String(hour).padStart(2, '0');
      }
      if (clockMinutes) {
        clockMinutes.textContent = String(now.getMinutes()).padStart(2, '0');
      }
      if (liveDate) {
        liveDate.textContent = new Intl.DateTimeFormat(undefined, {
          weekday: 'long', day: 'numeric', month: 'short', year: 'numeric',
        }).format(now);
        liveDate.dateTime = [now.getFullYear(), String(now.getMonth() + 1).padStart(2, '0'), String(now.getDate()).padStart(2, '0')].join('-');
      }
      if (timeGreeting) {
        const greeting = hour >= 5 && hour < 12
          ? 'Good morning'
          : hour >= 12 && hour < 17
            ? 'Good afternoon'
            : hour >= 17 && hour < 21
              ? 'Good evening'
              : 'Welcome back';
        timeGreeting.textContent = greeting;
      }
      if (dashboardHero) {
        dashboardHero.dataset.daypart = hour >= 5 && hour < 12
          ? 'morning'
          : hour >= 12 && hour < 17
            ? 'day'
            : hour >= 17 && hour < 21
              ? 'evening'
              : 'night';
      }
    };
    updateClock();
    window.setInterval(updateClock, 15000);
  }

  const streakReset = document.querySelector('[data-streak-reset]');
  if (streakReset) {
    const nextDay = new Date();
    nextDay.setHours(24, 0, 0, 0);
    const millisecondsUntilNextDay = Math.max(1000, nextDay.getTime() - Date.now());
    const updateStreakReset = () => {
      const millisecondsLeft = Math.max(0, nextDay.getTime() - Date.now());
      const minutesLeft = Math.floor(millisecondsLeft / 60000);
      const hours = Math.floor(minutesLeft / 60);
      const minutes = minutesLeft % 60;
      streakReset.textContent = 'New day in ' + hours + 'h ' + minutes + 'm';
    };
    updateStreakReset();
    window.setInterval(updateStreakReset, 60000);
    window.setTimeout(() => window.location.reload(), millisecondsUntilNextDay + 750);
  }

  document.querySelectorAll('form[data-confirm]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });

  const menuToggle = document.querySelector('[data-menu-toggle]');
  const sidebar = document.querySelector('#sidebar');
  menuToggle?.addEventListener('click', () => sidebar?.classList.toggle('open'));
  document.addEventListener('click', (event) => {
    if (sidebar?.classList.contains('open') && !sidebar.contains(event.target) && !menuToggle?.contains(event.target)) {
      sidebar.classList.remove('open');
    }
  });

  document.querySelectorAll('[data-prompt]').forEach((button) => {
    button.addEventListener('click', () => {
      const input = document.querySelector('.chat-input textarea');
      if (input) {
        input.value = button.dataset.prompt || '';
        input.focus();
      }
    });
  });

  const voiceButton = document.querySelector('[data-voice-input]');
  const voiceStatus = document.querySelector('[data-voice-status]');
  const questionInput = document.querySelector('[data-chat-form] textarea');
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (voiceButton && voiceStatus && questionInput) {
    if (!SpeechRecognition) {
      voiceButton.disabled = true;
      voiceStatus.textContent = 'Voice input is not supported in this browser. You can type your question instead.';
    } else {
      const recognition = new SpeechRecognition();
      let isListening = false;
      let gotVoiceResult = false;
      let stoppedByUser = false;
      let recognitionError = '';
      recognition.lang = navigator.language || 'en-US';
      recognition.interimResults = false;
      recognition.continuous = false;
      recognition.maxAlternatives = 1;

      const setListening = (listening) => {
        isListening = listening;
        voiceButton.classList.toggle('is-listening', listening);
        voiceButton.querySelector('span').textContent = listening ? 'Stop' : 'Speak';
        voiceButton.setAttribute('aria-label', listening ? 'Stop voice input' : 'Start voice input');
      };

      voiceButton.addEventListener('click', () => {
        if (isListening) {
          stoppedByUser = true;
          recognition.stop();
          return;
        }
        gotVoiceResult = false;
        stoppedByUser = false;
        recognitionError = '';
        try {
          recognition.start();
          voiceStatus.textContent = 'Listening… speak your study question.';
        } catch (_error) {
          voiceStatus.textContent = 'Could not start the microphone. Please try again.';
        }
      });

      recognition.onstart = () => setListening(true);
      recognition.onresult = (event) => {
        const transcript = event.results?.[0]?.[0]?.transcript?.trim();
        if (transcript) {
          gotVoiceResult = true;
          questionInput.value = transcript;
          questionInput.focus();
          voiceStatus.textContent = 'Transcript ready. Review it, then tap Send.';
        }
      };
      recognition.onerror = (event) => {
        const messages = {
          'not-allowed': 'Microphone access was denied. Allow access in your browser settings.',
          'service-not-allowed': 'Speech recognition is unavailable in this browser.',
          'no-speech': 'No speech was detected. Try again or type your question.',
          network: 'Voice recognition needs a network connection in this browser.',
        };
        recognitionError = messages[event.error] || 'Voice input could not start. Try again or type your question.';
      };
      recognition.onend = () => {
        setListening(false);
        if (recognitionError) voiceStatus.textContent = recognitionError;
        else if (gotVoiceResult) voiceStatus.textContent = 'Transcript ready. Review it, then tap Send.';
        else if (stoppedByUser) voiceStatus.textContent = 'Microphone stopped. You can try again or type your question.';
        else voiceStatus.textContent = 'No speech was detected. Try again or type your question.';
      };
    }
  }

  const speakAnswerButton = document.querySelector('[data-speak-answer]');
  const stopSpeakingButton = document.querySelector('[data-stop-speaking]');
  const answerText = document.querySelector('.answer-text');
  if (speakAnswerButton && answerText) {
    if (!('speechSynthesis' in window) || !('SpeechSynthesisUtterance' in window)) {
      speakAnswerButton.disabled = true;
      speakAnswerButton.title = 'Spoken replies are not supported in this browser.';
    } else {
      speakAnswerButton.addEventListener('click', () => {
        window.speechSynthesis.cancel();
        const reply = new SpeechSynthesisUtterance(answerText.textContent.trim());
        reply.lang = navigator.language || 'en-US';
        reply.rate = 0.96;
        reply.onstart = () => {
          if (stopSpeakingButton) stopSpeakingButton.hidden = false;
        };
        reply.onend = () => {
          if (stopSpeakingButton) stopSpeakingButton.hidden = true;
        };
        reply.onerror = () => {
          if (stopSpeakingButton) stopSpeakingButton.hidden = true;
        };
        window.speechSynthesis.speak(reply);
      });
      stopSpeakingButton?.addEventListener('click', () => {
        window.speechSynthesis.cancel();
        stopSpeakingButton.hidden = true;
      });
    }
  }

  const timer = document.querySelector('[data-timer]');
  if (!timer) return;

  const timeDisplay = timer.querySelector('[data-time]');
  const labelDisplay = timer.querySelector('[data-label]');
  const startButton = timer.querySelector('[data-start]');
  const resetButton = timer.querySelector('[data-reset]');
  const helper = timer.querySelector('.timer-helper');
  const tabs = [...timer.querySelectorAll('[data-mode]')];
  const labels = { focus: 'Focus time', short: 'Short break', long: 'Long break' };
  let mode = 'focus';
  let selectedMinutes = 25;
  let secondsLeft = selectedMinutes * 60;
  let intervalId = null;

  const renderTime = () => {
    const minutes = Math.floor(secondsLeft / 60).toString().padStart(2, '0');
    const seconds = (secondsLeft % 60).toString().padStart(2, '0');
    timeDisplay.textContent = `${minutes}:${seconds}`;
  };

  const stopTimer = () => {
    if (intervalId !== null) window.clearInterval(intervalId);
    intervalId = null;
  };

  const finishTimer = async () => {
    stopTimer();
    secondsLeft = 0;
    renderTime();
    startButton.textContent = 'Session complete';
    startButton.disabled = true;
    labelDisplay.textContent = mode === 'focus' ? 'Well done!' : 'Break complete';
    if (mode !== 'focus') return;

    helper.textContent = 'Saving your completed focus session…';
    try {
      const response = await fetch('/pomodoro/complete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ minutes: selectedMinutes }),
      });
      if (!response.ok) throw new Error('Could not save session');
      const stats = await response.json();
      helper.textContent = stats.message || 'Focus session saved. Nice work!';
      const count = document.querySelector('[data-session-count]');
      if (count && Number.isFinite(stats.sessions_today)) count.textContent = stats.sessions_today;
      const hours = document.querySelector('[data-total-hours]');
      if (hours && Number.isFinite(stats.hours_today)) hours.textContent = stats.hours_today;
      const list = document.querySelector('[data-session-list]');
      if (list && Number.isFinite(stats.sessions_today)) {
        const empty = list.querySelector('.muted');
        empty?.remove();
        const item = document.createElement('div');
        const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        item.innerHTML = `<span class="session-check">✓</span><span>${selectedMinutes} minute focus</span><time>${time}</time>`;
        list.prepend(item);
      }
    } catch (_error) {
      helper.textContent = 'The session finished, but could not be saved. Check that the Flask app is still running.';
    }
  };

  tabs.forEach((tab) => {
    tab.addEventListener('click', () => {
      stopTimer();
      tabs.forEach((item) => item.classList.toggle('active', item === tab));
      mode = tab.dataset.mode;
      selectedMinutes = Number(tab.dataset.minutes) || 25;
      secondsLeft = selectedMinutes * 60;
      labelDisplay.textContent = labels[mode];
      startButton.disabled = false;
      startButton.textContent = mode === 'focus' ? 'Start focus' : 'Start break';
      helper.textContent = 'A common rhythm is 25 minutes of focus followed by a 5-minute break.';
      renderTime();
    });
  });

  startButton.addEventListener('click', () => {
    if (intervalId !== null) {
      stopTimer();
      startButton.textContent = 'Resume';
      return;
    }
    if (secondsLeft <= 0) return;
    startButton.textContent = 'Pause';
    intervalId = window.setInterval(() => {
      secondsLeft -= 1;
      renderTime();
      if (secondsLeft <= 0) finishTimer();
    }, 1000);
  });

  resetButton.addEventListener('click', () => {
    stopTimer();
    secondsLeft = selectedMinutes * 60;
    startButton.disabled = false;
    startButton.textContent = mode === 'focus' ? 'Start focus' : 'Start break';
    labelDisplay.textContent = labels[mode];
    helper.textContent = 'A common rhythm is 25 minutes of focus followed by a 5-minute break.';
    renderTime();
  });
});
