import * as jose from 'jose';
import { Buffer } from 'buffer'; // Import Buffer

// Define an interface for the expected key structure
interface EncryptionKey {
  version: number;
  keyMaterial: {
    algorithm: 'RSA_OAEP_256'; // Ensure specific algorithm
    keyMaterial: string; // Base64 encoded SPKI public key (without headers/footers)
  };
  scope: 'PAYLOAD_ENCRYPTION';
}

async function encryptPayload(jsonKeyString: string, plaintext: string): Promise<string> {
  let keyData: EncryptionKey;

  // 1. Parse and validate the input JSON key string
  try {
    keyData = JSON.parse(jsonKeyString);
    // Basic validation
    if (
      keyData?.version !== 1 ||
      keyData?.keyMaterial?.algorithm !== 'RSA_OAEP_256' ||
      !keyData?.keyMaterial?.keyMaterial ||
      keyData?.scope !== 'PAYLOAD_ENCRYPTION'
    ) {
      throw new Error('Invalid key structure or missing required fields.');
    }
  } catch (error) {
    throw new Error(`Failed to parse JSON key: ${error instanceof Error ? error.message : String(error)}`);
  }

  // 2. Format the PEM public key from the keyMaterial
  // The key material seems to be the base64 part of a SPKI PEM key.
  // We need to wrap it with the standard PEM headers/footers.
  const base64Key = keyData.keyMaterial.keyMaterial;
  const pemKey = `-----BEGIN PUBLIC KEY-----\n${base64Key.match(/.{1,64}/g)?.join('\n')}\n-----END PUBLIC KEY-----`;

  // 3. Import the public key
  let publicKey: jose.KeyLike;
  try {
    // RSA-OAEP-256 is the JWE algorithm, importSPKI infers the key's algorithm
    publicKey = await jose.importSPKI(pemKey, 'RSA-OAEP-256');
    // Note: 'RSA-OAEP-256' is specified here as the *intended usage algorithm* for the key,
    // matching the JWE 'alg'. `importSPKI` itself will validate the key format (e.g., RSA).
  } catch (error) {
    throw new Error(`Failed to import public key: ${error instanceof Error ? error.message : String(error)}`);
  }

  // 4. Encrypt the plaintext using JWE Compact Serialization
  try {
    const jwe = await new jose.CompactEncrypt(
      new TextEncoder().encode(plaintext) // Encode the plaintext payload
    )
    .setProtectedHeader({
      alg: 'RSA-OAEP-256', // Key Encryption Algorithm [1]
      enc: 'A256GCM'        // Content Encryption Algorithm (AES GCM 256-bit) [1]
    })
    .encrypt(publicKey); // Encrypt using the imported public key

    return jwe;
  } catch (error) {
    throw new Error(`Failed to encrypt payload: ${error instanceof Error ? error.message : String(error)}`);
  }
}

// --- CLI Execution ---

// Bun provides command-line arguments in Bun.argv [2]
// Bun.argv[0] = bun executable path
// Bun.argv[1] = script path (encrypt.ts)
// Bun.argv[2] = first user argument (jsonKeyString)
// Bun.argv[3] = second user argument (plaintext)

if (Bun.argv.length < 4) {
  console.error("Usage: bun run encrypt.ts '<json_key_string>' '<plaintext_string>'");
  console.error("\nExample:");
  console.error(`  bun run encrypt.ts '{"version": 1, "keyMaterial": {"algorithm": "RSA_OAEP_256", "keyMaterial": "MIIBIjAN...AQAB"}, "scope": "PAYLOAD_ENCRYPTION"}' 'hello world'`);
  process.exit(1);
}

const jsonKeyArg = Bun.argv[2];
const plaintextArg = Bun.argv[3];

encryptPayload(jsonKeyArg, plaintextArg)
  .then(jweString => {
    console.log(jweString);
  })
  .catch(error => {
    console.error("Error:", error.message);
    process.exit(1);
  });