<?php
/**
 * availability.php — live Airbnb → website calendar sync for Suite 507.
 *
 * Fetches your Airbnb iCal export server-side, parses the booked/blocked date
 * ranges, and returns them as JSON for the booking calendar to consume. Runs on
 * Hostinger's built-in PHP — no extra service needed.
 *
 * SETUP: paste your Airbnb "Export calendar" (.ics) link into $ICAL_URLS below.
 * Get it at airbnb.com → Listing → Calendar → Availability → Connect calendars
 * → Export calendar. Keep this link private — it lives here on the server and is
 * never exposed to visitors (PHP runs server-side).
 */

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Cache-Control: no-cache');

// ── CONFIG ───────────────────────────────────────────────────────────────────
$ICAL_URLS = [
  'PASTE_YOUR_AIRBNB_ICAL_URL_HERE',
  // You can add more feeds here (e.g. VRBO/Booking.com) — all get merged.
];
$CACHE_FILE = __DIR__ . '/.availability-cache.json';
$CACHE_TTL  = 900; // seconds (15 min) — how long before we re-poll Airbnb

// ── Serve fresh cache if we have it (keeps the page fast, is kind to Airbnb) ──
if (is_file($CACHE_FILE) && (time() - filemtime($CACHE_FILE) < $CACHE_TTL)) {
  echo file_get_contents($CACHE_FILE);
  exit;
}

// ── Fetch + parse each iCal feed ─────────────────────────────────────────────
function fetch_ics($url) {
  if (function_exists('curl_init')) {
    $ch = curl_init($url);
    curl_setopt_array($ch, [
      CURLOPT_RETURNTRANSFER => true,
      CURLOPT_FOLLOWLOCATION => true,
      CURLOPT_TIMEOUT        => 15,
      CURLOPT_USERAGENT      => 'CaribedenCalendar/1.0',
    ]);
    $body = curl_exec($ch);
    curl_close($ch);
    if ($body !== false) return $body;
  }
  return @file_get_contents($url); // fallback if cURL is unavailable
}

$ranges = [];
foreach ($ICAL_URLS as $url) {
  if (strpos($url, 'PASTE_YOUR') === 0) continue; // not configured yet
  $ics = fetch_ics($url);
  if ($ics === false || $ics === null) {
    // Fetch failed → serve stale cache rather than showing everything as free.
    if (is_file($CACHE_FILE)) { echo file_get_contents($CACHE_FILE); exit; }
    continue;
  }
  $ics = preg_replace("/\r\n[ \t]/", '', $ics); // unfold RFC 5545 folded lines
  foreach (preg_split('/BEGIN:VEVENT/', $ics) as $chunk) {
    if (strpos($chunk, 'DTSTART') === false) continue;
    if (preg_match('/DTSTART[^:]*:(\d{8})/', $chunk, $s) &&
        preg_match('/DTEND[^:]*:(\d{8})/',   $chunk, $e)) {
      // Airbnb's DTEND is the checkout day (exclusive) — exactly what the
      // calendar expects, so that final night stays bookable.
      $ranges[] = [
        'start' => substr($s[1],0,4).'-'.substr($s[1],4,2).'-'.substr($s[1],6,2),
        'end'   => substr($e[1],0,4).'-'.substr($e[1],4,2).'-'.substr($e[1],6,2),
      ];
    }
  }
}

$out = json_encode(['updated' => date('c'), 'ranges' => $ranges]);
@file_put_contents($CACHE_FILE, $out); // best-effort cache write
echo $out;
