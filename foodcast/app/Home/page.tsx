"use client";
import Link from "next/link";
import Header from "../components/Header";
import Footer from "../components/Footer";
import ForecastChart from "../components/ForecastChart";
import { products } from "../data/products";
import {
  TrendingUp,
  TrendingDown,
  BarChart3,
  Shield,
  Zap,
  Users,
  ChevronRight,
  Sparkles,
  Target,
} from "lucide-react";

const trendingProducts = products.slice(0, 6);
const featuredProduct = products[0];

const Homepage = () => {
  return (
    <>
      <Header />

      {/* ===== HERO SECTION ===== */}
      <section className="hero-section">
        {/* Wave background */}
        <div className="hero-wave-bg" />

        {/* Decorative floating shapes */}
        <div
          style={{
            position: "absolute",
            top: "15%",
            right: "10%",
            width: 200,
            height: 200,
            borderRadius: "50%",
            background: "rgba(126,217,87,0.05)",
            animation: "float 6s ease-in-out infinite",
          }}
        />
        <div
          style={{
            position: "absolute",
            bottom: "25%",
            left: "5%",
            width: 150,
            height: 150,
            borderRadius: "50%",
            background: "rgba(255,145,77,0.05)",
            animation: "float 8s ease-in-out infinite 1s",
          }}
        />

        <div className="hero-content">
          <div className="hero-left animate-slide-left">
            <div className="hero-badge">
              <Sparkles size={14} />
              AI Price Analytics System
            </div>
            <h1 className="hero-title">
              See Next Week&apos;s Price Forecast
            </h1>
            <p className="hero-subtitle">NCR Agri-Fishery Markets</p>
            <p className="hero-description">
              AI-Based Forecasting and Market Analysis of Agri-Fishery Food Prices in NCR Markets using Algorithms.
            </p>

            <div className="hero-stats">
              <div className="hero-stat">
                <span className="hero-stat-value">12+</span> Crops
              </div>
              <div className="hero-stat">
                <span className="hero-stat-value">95%</span> Model Accuracy
              </div>
            </div>

            <div className="hero-cta-group">
              <Link href="/Search" className="btn-primary">
                Check Prices <ChevronRight size={18} />
              </Link>
              <Link href="/About" className="btn-outline">
                Learn More
              </Link>
            </div>
          </div>

          <div className="hero-right animate-slide-right">
            {/* Trending Panel */}
            <div className="trending-panel">
              <div className="trending-title">
                <TrendingUp size={18} />
                Trending
              </div>
              {trendingProducts.map((product) => (
                <div className="trending-item" key={product.id}>
                  <span className="trending-product-name">
                    {product.emoji} {product.name}
                  </span>
                  <span
                    className={`trending-price-change ${
                      product.change >= 0 ? "up" : "down"
                    }`}
                  >
                    {product.change >= 0 ? (
                      <TrendingUp size={12} style={{ display: "inline", marginRight: 4 }} />
                    ) : (
                      <TrendingDown size={12} style={{ display: "inline", marginRight: 4 }} />
                    )}
                    {product.change >= 0 ? "+" : ""}
                    {product.change}%
                  </span>
                </div>
              ))}
              <Link href="/Search" className="view-trends-btn">
                View Market Trends →
              </Link>
            </div>
          </div>
        </div>

        {/* Forecast Card */}
        <div
          style={{
            position: "absolute",
            bottom: "8%",
            left: "50%",
            transform: "translateX(-50%)",
            width: "85%",
            maxWidth: 1200,
            zIndex: 3,
          }}
          className="animate-fade-in-up delay-300"
        >
          <div className="forecast-card">
            <div className="forecast-card-header">
              <div className="forecast-card-title">
                {featuredProduct.emoji} Premium Rice Market Forecast
              </div>
            </div>
            <div className="forecast-metrics">
              <div className="forecast-metric">
                <span className="forecast-metric-label">Current Price</span>
                <span className="forecast-metric-value current">
                  ₱{featuredProduct.currentPrice.toFixed(2)}
                </span>
              </div>
              <div className="forecast-metric">
                <span className="forecast-metric-label">Predicted Price</span>
                <span className="forecast-metric-value predicted">
                  ₱{featuredProduct.predictedPrice.toFixed(2)}
                </span>
              </div>
              <div className="forecast-metric">
                <span className="forecast-metric-label">Confidence</span>
                <span className="forecast-metric-value confidence">
                  {featuredProduct.confidence}%
                </span>
              </div>
            </div>
            <ForecastChart data={featuredProduct.chartData} height={220} />
          </div>
        </div>
      </section>

      {/* Extra spacer for the forecast card overlap */}
      <div style={{ height: 160 }} />

      {/* ===== WHY USE THIS PLATFORM ===== */}
      <section className="features-section features-section-alt">
        <h2 className="features-title animate-fade-in-up">Why Use This Platform?</h2>
        <p className="features-description animate-fade-in-up delay-100">
          FOODCAST analyzes historical market data and applies advanced machine learning models to
          generate accurate price forecasts. Designed for farmers, traders, researchers, and policymakers.
        </p>

        <div className="features-tabs animate-fade-in-up delay-200">
          <span className="feature-tab active">Feature 1</span>
          <span className="feature-tab">Feature 2</span>
          <span className="feature-tab">Feature 3</span>
          <span className="feature-tab">Feature 4</span>
        </div>

        <div className="features-grid">
          <div className="feature-card animate-fade-in-up delay-100">
            <div className="feature-icon">
              <BarChart3 size={28} />
            </div>
            <h3>AI-Powered Forecasts</h3>
            <p>Advanced machine learning algorithms provide highly accurate price predictions for the upcoming weeks.</p>
          </div>
          <div className="feature-card animate-fade-in-up delay-200">
            <div className="feature-icon">
              <Shield size={28} />
            </div>
            <h3>Verified Data Sources</h3>
            <p>All market data is sourced from verified NCR markets, ensuring reliability and trustworthiness.</p>
          </div>
          <div className="feature-card animate-fade-in-up delay-300">
            <div className="feature-icon">
              <Zap size={28} />
            </div>
            <h3>Real-Time Updates</h3>
            <p>Prices and forecasts are updated weekly to reflect the latest market conditions and trends.</p>
          </div>
          <div className="feature-card animate-fade-in-up delay-400">
            <div className="feature-icon">
              <Users size={28} />
            </div>
            <h3>Built for Everyone</h3>
            <p>From farmers to researchers — our platform is designed to be intuitive and accessible to all.</p>
          </div>
        </div>
      </section>

      <Footer />
    </>
  );
};

export default Homepage;