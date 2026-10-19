window.WBW_CONFIG = {
  // Google Sheet shared as "anyone with the link can view"; shops and run log are read live from it.
  sheetId: '1lSL2J0yV0bwj2PmBSaeVahCM67X6a8HQzxKXPmPvZ5k',
  shopsTab: 'shop metadata',
  logTab: 'Schedule and Assignments',
  // Apps Script web-app /exec URL (see apps_script.gs). Leave empty for local demo mode.
  votesUrl: 'https://script.google.com/macros/s/AKfycbxYkGowcSGYzjAr2Wr2BA4umX3ihAScGcsluyGIm_ILICVX8t7bllmKLFIWtv7WZUtq/exec',
  // Leader spellings to merge in the run log.
  leaderAliases: { 'James': 'James U', 'Steven': 'Steve' },
  pollSeconds: 15,
};
