import CryptoJS from 'crypto-js';

const SECRET = process.env.NEXT_PUBLIC_ID_SECRET || 'dev-secret-key';

export function encryptId(id: string): string {
  try {
    const encrypted = CryptoJS.AES.encrypt(id, SECRET).toString();
    return encodeURIComponent(encrypted);
  } catch (e) {
    return encodeURIComponent(id);
  }
}

export function decryptId(token: string): string {
  try {
    const decoded = decodeURIComponent(token);
    const bytes = CryptoJS.AES.decrypt(decoded, SECRET);
    const original = bytes.toString(CryptoJS.enc.Utf8);
    return original || token;
  } catch (e) {
    return token;
  }
}

export default { encryptId, decryptId };
