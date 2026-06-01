import { fetchProducts } from "../../lib/data";
import { encryptId, decryptId } from "../../../lib/idCipher";
import Product from "../../client/Product";

export async function generateStaticParams() {
  const products = await fetchProducts();
  return products.map((p) => ({
    id: encryptId(p.id),
  }));
}

export const dynamic = 'force-static';
export const revalidate = 3600;

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const products = await fetchProducts();
  const { id: encryptedId } = await params;
  const productId = decryptId(encryptedId);

  // Keep full data for the target product and its variants (same name),
  // strip heavy forecast arrays from everything else to reduce payload.
  // SWR will fetch full data in the background if needed.
  const targetProduct = products.find(p => p.id === productId);
  const targetName = targetProduct?.name;

  const optimizedProducts = products.map(p => {
    if (p.id === productId || p.name === targetName) return p;
    return { ...p, forecastData: [], dailyForecast: [] };
  });

  return <Product params={params} initialProducts={optimizedProducts} />;
}
