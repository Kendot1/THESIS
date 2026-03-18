import Link from "next/link";
import SparklineChart from "./SparklineChart";

interface ProductCardProps {
  id: string;
  name: string;
  emoji: string;
  currentPrice: number;
  predictedPrice: number;
  sparklineData: { value: number }[];
}

const ProductCard = ({ id, name, emoji, currentPrice, predictedPrice, sparklineData }: ProductCardProps) => {
  return (
    <Link href={`/Product/${id}`} className="product-card">
      <div className="product-card-image">
        <span style={{ fontSize: "3rem" }}>{emoji}</span>
      </div>
      <div className="product-card-name">{name}</div>
      <div className="product-card-prices">
        <div className="product-card-price">
          <span className="product-card-price-label">Current</span>
          <span className="product-card-price-value current">₱{currentPrice.toFixed(2)}</span>
        </div>
        <div className="product-card-price">
          <span className="product-card-price-label">Predicted</span>
          <span className="product-card-price-value predicted">₱{predictedPrice.toFixed(2)}</span>
        </div>
      </div>
      <div className="product-card-sparkline">
        <SparklineChart data={sparklineData} />
      </div>
    </Link>
  );
};

export default ProductCard;
