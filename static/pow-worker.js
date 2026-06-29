// Web Worker that brute-forces a SHA-256 proof-of-work nonce.
// Expects a message: { challenge: string, difficulty: number }
// Posts back:         { nonce: string }

self.onmessage = async function (event) {
  const { challenge, difficulty } = event.data;
  let nonce = 0;

  while (true) {
    const input = challenge + nonce.toString();
    const hashBuffer = await crypto.subtle.digest(
      "SHA-256",
      new TextEncoder().encode(input)
    );
    const hashArray = new Uint8Array(hashBuffer);

    if (hasLeadingZeroBits(hashArray, difficulty)) {
      self.postMessage({ nonce: nonce.toString() });
      return;
    }

    nonce++;
  }
};

function hasLeadingZeroBits(hashBytes, difficulty) {
  let zeroBitsFound = 0;
  for (const byte of hashBytes) {
    if (zeroBitsFound + 8 <= difficulty) {
      if (byte !== 0) return false;
      zeroBitsFound += 8;
    } else {
      const remaining = difficulty - zeroBitsFound;
      const mask = 0xff >> (8 - remaining);
      // The top `remaining` bits must be zero.
      return (byte >> (8 - remaining)) === 0;
    }
    if (zeroBitsFound >= difficulty) return true;
  }
  return zeroBitsFound >= difficulty;
}
