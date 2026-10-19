/** @OnlyCurrentDoc */
// We Brake for Wildlife Coffee Club: vote backend.
// Paste into the sheet's Extensions > Apps Script, then Deploy > New deployment > Web app
// (Execute as: Me, Who has access: Anyone). Copy the /exec URL into site/config.js.
//
// Votes are an append-only log in the "votes" tab (created automatically):
//   timestamp | voter | voter_key | shop | vote (1 = 👍, 0 = removed)
// The latest row per (voter_key, shop) wins, so the full history is kept.

const VOTING_OPEN = true;          // set false (and redeploy) to freeze results
const VOTES_TAB = 'votes';
const SHOPS_TAB = 'shop metadata';

function doGet() {
  return json_(tally_());
}

function doPost(e) {
  if (!VOTING_OPEN) return json_({ error: 'Voting is closed.' });
  let body;
  try { body = JSON.parse(e.postData.contents); } catch (err) { return json_({ error: 'Bad request.' }); }

  const voter = String(body.voter || '').replace(/\s+/g, ' ').trim().slice(0, 40);
  const shop = String(body.shop || '');
  if (!voter) return json_({ error: 'Name required.' });

  const shops = SpreadsheetApp.getActive().getSheetByName(SHOPS_TAB).getDataRange().getValues();
  const header = shops[0];
  const row = shops.find(r => r[header.indexOf('shop')] === shop);
  if (!row) return json_({ error: 'Unknown shop.' });
  if (String(row[header.indexOf('status')]).toLowerCase() === 'closed') return json_({ error: 'That shop is closed.' });

  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    votesSheet_().appendRow([new Date(), voter, voter.toLowerCase(), shop, body.vote ? 1 : 0]);
  } finally {
    lock.releaseLock();
  }
  return json_(tally_());
}

function tally_() {
  const rows = votesSheet_().getDataRange().getValues().slice(1);
  const latest = {};   // "key|shop" -> {voter, shop, vote}
  const names = {};    // key -> most recent spelling of the name
  rows.forEach(([, voter, key, shop, vote]) => {
    latest[key + '|' + shop] = { key, shop, vote: Number(vote) };
    names[key] = voter;
  });
  const votes = {};
  Object.values(latest).forEach(v => {
    if (!v.vote) return;
    (votes[v.shop] = votes[v.shop] || []).push(names[v.key]);
  });
  return { open: VOTING_OPEN, votes, voters: Object.values(names).sort() };
}

function votesSheet_() {
  const ss = SpreadsheetApp.getActive();
  let sh = ss.getSheetByName(VOTES_TAB);
  if (!sh) {
    sh = ss.insertSheet(VOTES_TAB);
    sh.appendRow(['timestamp', 'voter', 'voter_key', 'shop', 'vote']);
    sh.setFrozenRows(1);
  }
  return sh;
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
