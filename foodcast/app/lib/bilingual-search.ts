/**
 * Dynamic Bilingual Search (English <-> Tagalog / Filipino) for FOODCAST.
 * Enables seamless search whether the user types in English, Tagalog,
 * or common Filipino agricultural market names / colloquial aliases.
 */

// Category-level translations (matching full categories)
const CATEGORY_TRANSLATIONS: Record<string, string[]> = {
  "rice": ["bigas", "kanin"],
  "vegetables": ["gulay", "halaman"],
  "fish": ["isda", "lamang-dagat", "seafood"],
  "meat": ["karne"],
  "poultry": ["manok", "manukan", "poltri"],
  "livestock": ["karne", "hayop"],
  "fruits": ["prutas"],
  "spices": ["pampalasa", "rekado"],
  "corn": ["mais"],
  "oils": ["mantika", "langis"],
  "sugar": ["asukal"],
};

// Commodity-level bidirectional mappings
const COMMODITY_TRANSLATIONS: Record<string, string[]> = {
  // Grains & Sugar
  "rice": ["bigas", "kanin", "palay", "sinandomeng", "dinorado", "malagkit"],
  "sugar": ["asukal"],
  "corn": ["mais"],
  "corn cracked": ["binasag na mais", "mais"],
  "corn grits": ["grits ng mais", "mais"],
  "yellow sweet corn": ["dilaw na mais", "sweet corn", "mais"],

  // Vegetables
  "eggplant": ["talong"],
  "tomato": ["kamatis"],
  "cabbage": ["repolyo"],
  "carrot": ["karot"],
  "potato": ["patatas"],
  "bittergourd": ["ampalaya", "amargoso", "bitter melon", "bitter gourd"],
  "chayote": ["sayote"],
  "squash": ["kalabasa", "pumpkin"],
  "string beans": ["sitaw", "long beans"],
  "baguio beans": ["bitsuelas", "habitchuelas", "green beans"],
  "bell pepper": ["siling bell", "sweet pepper", "capsicum", "atsuete"],
  "broccoli": ["brokoli"],
  "cauliflower": ["koliplor"],
  "celery": ["kintsay", "kinchay"],
  "lettuce": ["letsugas", "iceberg", "romaine", "green ice"],
  "pechay baguio": ["pechay baguio", "petsay baguio", "wombok", "chinese cabbage"],
  "pechay tagalog": ["pechay tagalog", "petsay tagalog", "petsay", "bok choy"],
  "pechay": ["petsay", "bok choy", "wombok"],
  "mung beans": ["monggo", "munggo", "balatong"],

  // Spices
  "chili": ["sili", "siling labuyo", "siling haba", "labuyo", "hot pepper"],
  "red onion": ["pulang sibuyas", "sibuyas na pula", "sibuyas tagalog"],
  "white onion": ["puting sibuyas", "sibuyas na puti"],
  "onion": ["sibuyas"],
  "garlic": ["bawang"],
  "ginger": ["luya"],

  // Fruits
  "banana": ["saging", "saba", "lakatan", "latundan", "senorita", "cavendish"],
  "calamansi": ["kalamansi", "dayap", "lemon", "lime"],
  "mango": ["mangga", "carabao mango", "piko"],
  "papaya": ["papaya", "papayang hilaw"],
  "watermelon": ["pakwan"],
  "melon": ["melon", "cantaloupe"],
  "avocado": ["abukado"],
  "pomelo": ["suha", "lukban"],

  // Fish & Seafood
  "milkfish": ["bangus"],
  "round scad": ["galunggong", "gg"],
  "tilapia": ["tilapia"],
  "indian mackerel": ["alumahan", "hasa-hasa", "tanigue"],
  "sardines": ["sardinas", "tamban"],
  "squid": ["pusit"],

  // Meat & Poultry
  "pork": ["baboy", "karne ng baboy"],
  "beef": ["baka", "karne ng baka", "punta y pecho"],
  "chicken": ["manok", "buong manok", "pitso", "hita", "pakpak", "dressed chicken"],
  "chicken egg": ["itlog ng manok", "itlog"],

  // Oils
  "coconut oil": ["mantika ng niyog", "langis ng niyog", "mantika"],
  "palm oil": ["mantika", "langis", "cooking oil"],

  // Origins & Variants
  "local": ["lokal", "pambansa", "pinoy"],
  "imported": ["inangkat", "imported", "banyaga"],
  "belly": ["liempo", "tiyan ng baboy", "pork belly"],
  "ham": ["kasim", "pigi", "hita", "pork ham"],
  "liempo": ["pork belly", "tiyan ng baboy", "belly"],
  "kasim": ["pork shoulder", "paypay", "ham"],
  "brisket": ["punta y pecho", "tadyang"],
  "rump": ["pigi ng baka", "pigi"],
  "red": ["pula", "pulang"],
  "white": ["puti", "puting"],
  "washed": ["asukal na pula", "pula"],
  "refined": ["asukal na puti", "puti"],
  "brown": ["asukal na pula", "pula"]
};

// Reverse lookup index: Tagalog / Alias term -> Canonical terms
const REVERSE_COMMODITIES: Record<string, string[]> = {};
for (const [canonical, aliases] of Object.entries(COMMODITY_TRANSLATIONS)) {
  for (const alias of aliases) {
    if (!REVERSE_COMMODITIES[alias]) {
      REVERSE_COMMODITIES[alias] = [];
    }
    REVERSE_COMMODITIES[alias].push(canonical);
  }
}

const REVERSE_CATEGORIES: Record<string, string[]> = {};
for (const [canonical, aliases] of Object.entries(CATEGORY_TRANSLATIONS)) {
  for (const alias of aliases) {
    if (!REVERSE_CATEGORIES[alias]) {
      REVERSE_CATEGORIES[alias] = [];
    }
    REVERSE_CATEGORIES[alias].push(canonical);
  }
}

/**
 * Normalizes a string for search matching (lowercase, trims punctuation and extra spaces).
 */
export function normalizeSearchTerm(term: string): string {
  return (term || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "") // strip diacritics
    .replace(/[^a-z0-9\s-]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Extracts possible root stems from a Tagalog word (e.g., 'pulang' -> ['pulang', 'pula']).
 */
function extractTagalogStems(token: string): string[] {
  const stems = [token];
  if (token === "pulang") stems.push("pula");
  if (token === "puting") stems.push("puti");
  if (token === "isdang") stems.push("isda");
  if (token === "dilaw") stems.push("yellow");
  if (token === "binasag") stems.push("cracked");
  return stems;
}

/**
 * Checks whether an alias matches a query token safely without loose arbitrary sub-word collisions.
 */
function matchesAlias(alias: string, queryToken: string): boolean {
  if (alias === queryToken) return true;
  if (alias.startsWith(queryToken) && queryToken.length >= 3) return true;
  const words = alias.split(" ");
  return words.some(w => w === queryToken || (w.startsWith(queryToken) && queryToken.length >= 3));
}

/**
 * Checks whether a given product matches the user's search query in either English or Tagalog.
 */
export function matchesBilingualQuery(
  product: {
    name?: string;
    category?: string;
    variant?: string;
    origin?: string;
    description?: string;
  },
  rawQuery: string
): boolean {
  if (!rawQuery) return true;
  const q = normalizeSearchTerm(rawQuery);
  if (!q) return true;

  const name = normalizeSearchTerm(product.name || "");
  const category = normalizeSearchTerm(product.category || "");
  const variant = normalizeSearchTerm(product.variant || "");
  const origin = normalizeSearchTerm(product.origin || "");

  // Combined product text
  const productFull = `${name} ${category} ${variant} ${origin}`.trim();

  // 1. Direct match on English / database text
  // Short 1-2 char queries (e.g., "gg") must match whole words, avoiding substrings like "egg" or "eggplant"
  if (q.length <= 2) {
    const words = productFull.split(" ");
    if (words.some((w) => w === q)) return true;
  } else if (productFull.includes(q)) {
    return true;
  }

  // Check individual query tokens (e.g., "pulang sibuyas" -> ["pulang", "sibuyas"])
  const queryTokens = q.split(" ").filter((tok) => tok.length > 0);

  // 2. Expand product terms with dictionary synonyms (English -> Tagalog)
  const expandedProductTerms = new Set<string>();
  expandedProductTerms.add(name);
  expandedProductTerms.add(category);
  expandedProductTerms.add(variant);
  expandedProductTerms.add(origin);

  for (const field of [name, category, variant, origin]) {
    if (!field) continue;
    // Check direct commodity dictionary
    const comTerms = COMMODITY_TRANSLATIONS[field];
    if (comTerms) comTerms.forEach((t) => expandedProductTerms.add(normalizeSearchTerm(t)));

    // Check category dictionary
    const catTerms = CATEGORY_TRANSLATIONS[field];
    if (catTerms) catTerms.forEach((t) => expandedProductTerms.add(normalizeSearchTerm(t)));
  }

  // Check multi-word phrase containment
  for (const [canon, aliases] of Object.entries(COMMODITY_TRANSLATIONS)) {
    if (name === canon || name.includes(canon) || variant.includes(canon)) {
      aliases.forEach((a) => expandedProductTerms.add(normalizeSearchTerm(a)));
    }
  }

  const allProductTermsArray = Array.from(expandedProductTerms);
  const allProductText = allProductTermsArray.join(" ");

  // Direct substring check on expanded text (exclude short 2-character acronyms like 'gg')
  if (q.length > 2 && allProductText.includes(q)) {
    return true;
  }

  // 3. Multi-token Query Matching (e.g. "pulang sibuyas", "baboy liempo", "isda bangus")
  if (queryTokens.length > 1) {
    const allTokensSatisfied = queryTokens.every((rawToken: string) => {
      const stems = extractTagalogStems(rawToken);
      return stems.some((tok: string) => {
        // Direct match
        if (productFull.includes(tok) || allProductText.includes(tok)) {
          return true;
        }

        // Exact match in reverse commodity
        const canonComs = REVERSE_COMMODITIES[tok];
        if (canonComs && canonComs.some((c: string) => productFull.includes(c) || allProductText.includes(c))) {
          return true;
        }

        // Exact match in reverse category
        const canonCats = REVERSE_CATEGORIES[tok];
        if (canonCats && canonCats.some((c: string) => category.includes(c))) {
          return true;
        }

        return false;
      });
    });

    if (allTokensSatisfied) return true;
  }

  // 4. Single token matching (or acronym matching like 'gg')
  if (queryTokens.length === 1) {
    const token = queryTokens[0];
    const stems = extractTagalogStems(token);

    for (const stem of stems) {
      // Acronym / short token exact check
      if (stem === "gg") {
        return name.includes("round scad") || variant.includes("galunggong") || allProductTermsArray.includes("galunggong");
      }

      // Check reverse commodity translations
      for (const [alias, canonicals] of Object.entries(REVERSE_COMMODITIES)) {
        if (matchesAlias(alias, stem)) {
          if (canonicals.some((c: string) => productFull.includes(c))) {
            return true;
          }
        }
      }

      // Check reverse category translations
      for (const [alias, canonicals] of Object.entries(REVERSE_CATEGORIES)) {
        if (matchesAlias(alias, stem)) {
          if (canonicals.some((c: string) => category.includes(c))) {
            return true;
          }
        }
      }
    }
  }

  return false;
}
