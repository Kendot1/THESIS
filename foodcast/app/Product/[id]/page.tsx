"use client";
import { use } from "react";
import Header from "../../components/Header";
import Footer from "../../components/Footer";
import ForecastChart from "../../components/ForecastChart";
import ProductCard from "../../components/ProductCard";
import { products } from "../../data/products";
import {
  TrendingUp,
  TrendingDown,
  Info,
  Lightbulb,
  ArrowLeft,
  CheckCircle2,
} from "lucide-react";
import Link from "next/link";

interface ProductDetailProps {
  params: Promise<{ id: string }>;
}

const ProductDetailPage = ({ params }: ProductDetailProps) => {
  const { id } = use(params);
  const product = products.find((p) => p.id === id);

  if (!product) {
    return (
      <>
        <Header />
        <div
          style={{
            minHeight: "60vh",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexDirection: "column",
            gap: 16,
            paddingTop: 80,
          }}
        >
          <h1 style={{ fontFamily: "'Poppins', sans-serif", fontWeight: 700, fontSize: "1.5rem" }}>
            Product Not Found
          </h1>
          <Link href="/Search" className="btn-primary">
            <ArrowLeft size={16} /> Back to Search
          </Link>
        </div>
        <Footer />
      </>
    );
  }

  const suggestedProducts = products
    .filter((p) => p.id !== product.id && p.category === product.category)
    .slice(0, 4);

  const isUp = product.change >= 0;

  return (
    <>
      <Header />

      {/* ===== PRODUCT HEADER ===== */}
      <section className="product-detail-hero">
        <div className="product-detail-header animate-fade-in-up">
          <div className="product-detail-icon">
            <span style={{ fontSize: "2rem" }}>{product.emoji}</span>
          </div>
          <div>
            <h1 className="product-detail-name">{product.name}</h1>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 4 }}>
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 4,
                  padding: "4px 12px",
                  borderRadius: "var(--radius-full)",
                  background: isUp ? "rgba(126,217,87,0.2)" : "rgba(255,107,107,0.2)",
                  color: isUp ? "#7ED957" : "#FF6B6B",
                  fontSize: "0.85rem",
                  fontWeight: 600,
                }}
              >
                {isUp ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                {isUp ? "+" : ""}{product.change}%
              </span>
              <span style={{ color: "rgba(255,255,255,0.5)", fontSize: "0.85rem" }}>
                {product.category}
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* ===== MAIN CONTENT ===== */}
      <div className="product-detail-content">
        {/* Left: Chart */}
        <div className="detail-chart-card animate-slide-left">
          <div className="detail-chart-title">Product Forecast</div>
          <div className="forecast-metrics" style={{ marginBottom: 16 }}>
            <div className="forecast-metric">
              <span className="forecast-metric-label">Current Price</span>
              <span className="forecast-metric-value current">
                ₱{product.currentPrice.toFixed(2)}
              </span>
            </div>
            <div className="forecast-metric">
              <span className="forecast-metric-label">Predicted Price</span>
              <span className="forecast-metric-value predicted">
                ₱{product.predictedPrice.toFixed(2)}
              </span>
            </div>
            <div className="forecast-metric">
              <span className="forecast-metric-label">Confidence</span>
              <span className="forecast-metric-value confidence">
                {product.confidence}%
              </span>
            </div>
          </div>
          <div className="detail-chart-wrapper">
            <ForecastChart data={product.chartData} height={300} />
          </div>
        </div>

        {/* Right: Sidebar */}
        <div className="detail-sidebar animate-slide-right">
          {/* Price Overview */}
          <div className="detail-info-card">
            <h3>
              <Info size={18} color="var(--primary-green)" />
              Price Overview
            </h3>
            <div className="detail-info-row">
              <span className="detail-info-label">Current Price</span>
              <span className="detail-info-value">₱{product.currentPrice.toFixed(2)}</span>
            </div>
            <div className="detail-info-row">
              <span className="detail-info-label">Predicted Price</span>
              <span className="detail-info-value" style={{ color: "var(--primary-green)" }}>
                ₱{product.predictedPrice.toFixed(2)}
              </span>
            </div>
            <div className="detail-info-row">
              <span className="detail-info-label">Price Change</span>
              <span
                className="detail-info-value"
                style={{ color: isUp ? "var(--primary-green)" : "#FF6B6B" }}
              >
                {isUp ? "+" : ""}
                ₱{(product.predictedPrice - product.currentPrice).toFixed(2)}
              </span>
            </div>
            <div className="detail-info-row">
              <span className="detail-info-label">Confidence</span>
              <span className="detail-info-value">{product.confidence}%</span>
            </div>
            <div className="detail-info-row">
              <span className="detail-info-label">Category</span>
              <span className="detail-info-value">{product.category}</span>
            </div>
          </div>

          {/* Suggestive Insights */}
          <div className="detail-info-card">
            <h3>
              <Lightbulb size={18} color="var(--accent-orange)" />
              Suggestive Insights
            </h3>
            <div className="insight-item">
              <CheckCircle2 size={16} className="insight-icon" />
              <span>
                {isUp
                  ? `${product.name} prices are expected to increase by ${product.change}% next week, indicating growing demand.`
                  : `${product.name} prices are expected to decrease by ${Math.abs(product.change)}% next week due to increased supply.`
                }
              </span>
            </div>
            <div className="insight-item">
              <CheckCircle2 size={16} className="insight-icon" />
              <span>
                The model confidence level of {product.confidence}% suggests reliable forecast data based on historical trends.
              </span>
            </div>
            <div className="insight-item">
              <CheckCircle2 size={16} className="insight-icon" />
              <span>
                {isUp
                  ? "Consider purchasing before the projected price increase takes effect."
                  : "Prices may stabilize in the coming weeks as supply adjusts to demand."
                }
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* ===== SUGGESTED PRODUCTS ===== */}
      {suggestedProducts.length > 0 && (
        <section className="suggested-section">
          <h2 className="suggested-title">Suggested Products</h2>
          <div className="suggested-grid">
            {suggestedProducts.map((p) => (
              <ProductCard
                key={p.id}
                id={p.id}
                name={p.name}
                emoji={p.emoji}
                currentPrice={p.currentPrice}
                predictedPrice={p.predictedPrice}
                sparklineData={p.sparklineData}
              />
            ))}
          </div>
        </section>
      )}

      <Footer />
    </>
  );
};

export default ProductDetailPage;
