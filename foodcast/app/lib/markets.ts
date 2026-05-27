export interface MarketLocation {
  id: string;
  name: string;
  city: string;
  lat: number;
  lng: number;
  address: string;
  type: string;
  description: string;
  image?: string;
}

export const ncrMarkets: MarketLocation[] = [
  // San Juan
  { id: "agora", name: "Agora Market", city: "San Juan", lat: 14.6010, lng: 121.0350, address: "N. Domingo St., San Juan City", type: "Wet Market", description: "A bustling wet market in San Juan known for fresh vegetables, meat, and seafood at competitive prices." },
  // Muntinlupa
  { id: "alabang_central", name: "Alabang Central Market", city: "Muntinlupa", lat: 14.4230, lng: 121.0395, address: "Alabang-Zapote Rd., Alabang, Muntinlupa", type: "Wet Market", description: "One of the largest public markets in Muntinlupa, serving the Alabang area with fresh produce, fish, and poultry." },
  // Quezon City
  { id: "balintawak", name: "Balintawak (Cloverleaf) Market", city: "Quezon City", lat: 14.6573, lng: 120.9965, address: "EDSA cor. A. Bonifacio, Balintawak, Quezon City", type: "Wholesale & Wet Market", description: "One of Metro Manila's largest wholesale markets for fruits, vegetables, and root crops. A major supply hub for retailers across NCR." },
  // Taguig
  { id: "bicutan", name: "Bicutan Market", city: "Taguig", lat: 14.4890, lng: 121.0520, address: "Doña Soledad Ave., Bicutan, Taguig", type: "Wet Market", description: "A community wet market in Lower Bicutan offering fresh fish, meat, and everyday grocery items to Taguig residents." },
  // Pasay
  { id: "cartimar", name: "Cartimar Market", city: "Pasay", lat: 14.5493, lng: 120.9960, address: "Cartimar Ave., Pasay City", type: "Wet Market", description: "A well-known Pasay market offering fresh seafood, meats, and vegetables alongside pet supplies and other goods." },
  // Quezon City
  { id: "commonwealth", name: "Commonwealth Market", city: "Quezon City", lat: 14.6935, lng: 121.0870, address: "Commonwealth Ave., Quezon City", type: "Wet Market", description: "A busy neighborhood market in Commonwealth, QC, providing fresh produce, meat, and fish to nearby communities." },
  // Quezon City - Cubao
  { id: "farmers", name: "Farmers Market", city: "Quezon City", lat: 14.6198, lng: 121.0526, address: "Araneta City, Cubao, Quezon City", type: "Wet Market", description: "Located inside Araneta City, Cubao. Popular for affordable fresh fruits, vegetables, seafood, and local delicacies." },
  // Pateros
  { id: "grace", name: "Grace Marketplace", city: "Pateros", lat: 14.5435, lng: 121.0670, address: "M. Almeda St., Pateros", type: "Wet Market", description: "A compact market in Pateros known for local produce, fresh fish, and the town's famous balut (duck eggs)." },
  // Makati
  { id: "guadalupe", name: "Guadalupe Commercial Complex", city: "Makati", lat: 14.5636, lng: 121.0456, address: "J.P. Rizal St., Guadalupe Nuevo, Makati", type: "Wet Market", description: "A large commercial complex in Makati featuring a wet market with fresh seafood, meats, and vegetables alongside cooked food stalls." },
  // Parañaque
  { id: "la_huerta", name: "La Huerta Public Market", city: "Parañaque", lat: 14.4840, lng: 121.0030, address: "La Huerta, Parañaque City", type: "Wet Market", description: "A neighborhood market in Parañaque serving La Huerta residents with fresh produce, fish, and household essentials." },
  // Malabon
  { id: "malabon", name: "Malabon Central Market", city: "Malabon", lat: 14.6621, lng: 120.9570, address: "Rizal Ave., Malabon City", type: "Wet Market", description: "The main public market of Malabon City, renowned for fresh fish and seafood given the city's fishing heritage." },
  // Mandaluyong
  { id: "mandaluyong", name: "Mandaluyong Public Market", city: "Mandaluyong", lat: 14.5794, lng: 121.0344, address: "Kalentong St., Mandaluyong City", type: "Wet Market", description: "A well-organized public market in Mandaluyong offering fresh vegetables, meat, fish, and dry goods to the local community." },
  // Marikina
  { id: "marikina", name: "Marikina Public Market", city: "Marikina", lat: 14.6292, lng: 121.0973, address: "W. Paz St., Sta. Elena, Marikina City", type: "Wet Market", description: "The central public market of Marikina City, known for its cleanliness and wide selection of fresh food and local products." },
  // Caloocan
  { id: "maypajo", name: "Maypajo Public Market", city: "Caloocan", lat: 14.6530, lng: 120.9730, address: "Gen. San Miguel St., Maypajo, Caloocan City", type: "Wet Market", description: "A busy market in Caloocan offering affordable fresh produce, meats, and seafood to the densely populated Maypajo area." },
  // Quezon City
  { id: "mega_q_mart", name: "Mega Q-mart", city: "Quezon City", lat: 14.6235, lng: 121.0475, address: "EDSA, Cubao, Quezon City", type: "Wet Market", description: "A modern wet market in Cubao, QC, providing a wide range of fresh commodities including fruits, vegetables, and seafood." },
  // Quezon City
  { id: "munoz", name: "Muñoz Market", city: "Quezon City", lat: 14.6570, lng: 121.0200, address: "Muñoz, Quezon City", type: "Wet Market", description: "A neighborhood market near the Muñoz area of QC, popular for fresh vegetables, meat, and affordable daily essentials." },
  // Quezon City
  { id: "murphy", name: "Murphy Public Market", city: "Quezon City", lat: 14.6120, lng: 121.0330, address: "Murphy, Cubao, Quezon City", type: "Wet Market", description: "A compact community market near Cubao serving the Murphy district with fresh produce, fish, and meat at local prices." },
  // Pasig
  { id: "mutya_pasig", name: "Mutya ng Pasig Mega Market", city: "Pasig", lat: 14.5720, lng: 121.0656, address: "C. Raymundo Ave., Pasig City", type: "Wet Market", description: "One of Pasig's largest markets, offering a wide variety of fresh fish, meat, vegetables, and dry goods under one roof." },
  // Navotas
  { id: "navotas_agora", name: "Navotas Agora Market", city: "Navotas", lat: 14.6640, lng: 120.9430, address: "C-4 Road, Navotas City", type: "Fish Port / Wholesale", description: "A major fish and seafood wholesale hub in Navotas, supplying fresh catch from Manila Bay to markets across Metro Manila." },
  // Las Piñas
  { id: "new_las_pinas", name: "New Las Piñas City Public Market", city: "Las Piñas", lat: 14.4502, lng: 120.9830, address: "Alabang-Zapote Rd., Las Piñas City", type: "Wet Market", description: "The primary public market of Las Piñas City, offering fresh produce, meats, seafood, and local goods to south Metro Manila residents." },
  // Valenzuela
  { id: "new_marulas", name: "New Marulas Public Market", city: "Valenzuela", lat: 14.6940, lng: 120.9680, address: "Marulas, Valenzuela City", type: "Wet Market", description: "A renovated public market in Valenzuela serving the Marulas community with fresh fish, vegetables, and daily commodities." },
  // Manila
  { id: "obrero", name: "Obrero Public Market", city: "Manila", lat: 14.5630, lng: 121.0010, address: "Obrero St., Tondo, Manila", type: "Wet Market", description: "A traditional Manila market in Tondo offering fresh fish, vegetables, and meats at very affordable prices for local residents." },
  // Pasay
  { id: "pasay", name: "Pasay City Public Market", city: "Pasay", lat: 14.5375, lng: 120.9960, address: "F.B. Harrison St., Pasay City", type: "Wet Market", description: "The main public market of Pasay City, centrally located and known for fresh produce, meats, and seafood at competitive prices." },
  // Manila
  { id: "pritil", name: "Pritil Market", city: "Manila", lat: 14.6120, lng: 120.9720, address: "Pritil, Tondo, Manila", type: "Wet Market", description: "A historic market in Tondo, Manila, serving as a key source of fresh fish, vegetables, and meat for nearby communities." },
  // Manila
  { id: "quinta", name: "Quinta Market", city: "Manila", lat: 14.5920, lng: 120.9790, address: "Carlos Palanca St., Quiapo, Manila", type: "Wet Market", description: "One of Manila's oldest public markets near Quiapo, offering a wide variety of fresh produce, seafood, and local goods." },
  // Manila
  { id: "san_andres", name: "San Andres Market", city: "Manila", lat: 14.5710, lng: 121.0050, address: "A. Mabini St., San Andres, Manila", type: "Wet Market", description: "A well-known Manila market famous for fresh fruits, exotic produce, and imported goods at wholesale prices." },
  // Taguig
  { id: "taguig_peoples", name: "Taguig People's Market", city: "Taguig", lat: 14.5203, lng: 121.0760, address: "Gen. Luna St., Tuktukan, Taguig City", type: "Wet Market", description: "A community-oriented public market in Tuktukan, Taguig, providing fresh fish, meat, vegetables, and everyday essentials." },
  // Manila
  { id: "trabajo", name: "Trabajo Market", city: "Manila", lat: 14.6050, lng: 120.9800, address: "Juan Luna St., Tondo, Manila", type: "Wet Market", description: "A traditional wet market in Tondo, Manila, known for affordable fresh seafood, vegetables, and meats for local households." },
];

export function getNearestMarkets(
  markets: MarketLocation[], 
  userLat: number, 
  userLng: number
): (MarketLocation & { distance: number })[] {
  return markets.map(market => {
    // Haversine formula for distance in km
    const R = 6371;
    const dLat = (market.lat - userLat) * Math.PI / 180;
    const dLng = (market.lng - userLng) * Math.PI / 180;
    const a = 
      Math.sin(dLat/2) * Math.sin(dLat/2) +
      Math.cos(userLat * Math.PI / 180) * Math.cos(market.lat * Math.PI / 180) * 
      Math.sin(dLng/2) * Math.sin(dLng/2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    const distance = R * c;
    return { ...market, distance };
  }).sort((a, b) => a.distance - b.distance);
}
