"use client";
import { useState } from "react";
import Header from "../components/Header";
import Footer from "../components/Footer";
import ProductCard from "../components/ProductCard";
import ForecastChart from "../components/ForecastChart";
import { products } from "../data/products";
import { Search, TrendingUp, TrendingDown, ChevronRight } from "lucide-react";

const categories = ["All", "Crops", "Fish"];

const SearchPage = () => {
  const [searchQuery, setSearchQuery] = useState("");
  const [activeCategory, setActiveCategory] = useState("All");

  const filteredProducts = products.filter((p) => {
    const matchesSearch =
      p.name.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesCategory =
      activeCategory === "All" || p.category === activeCategory;
    return matchesSearch && matchesCategory;
  });

  // Featured forecast for the search page
  const featured = products[0];

  return (
    <>
      <Header />

      {/* ===== SEARCH HERO ===== */}
      <section className="search-hero">
        <div className="search-hero-wave" />
        <div style={{ position: "relative", zIndex: 2 }}>
          <h1 className="animate-fade-in-up">
            Check Future Prices of Farm and Fish Products
          </h1>
          <p className="animate-fade-in-up delay-100">
            See possible price changes for crops, vegetables, and seafood.
          </p>

          <div className="search-bar-container animate-fade-in-up delay-200">
            <div className="search-bar">
              <Search
                size={20}
                style={{
                  marginLeft: 18,
                  color: "#9CA3AF",
                  flexShrink: 0,
                }}
              />
              <input
                type="text"
                placeholder="Search for e.g., Rice, Fish, vegetables..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                id="search-input"
              />
              <button type="button">Search</button>
            </div>

            <div className="filter-tags" style={{ marginTop: 20 }}>
              {categories.map((cat) => (
                <button
                  key={cat}
                  className={`filter-tag ${activeCategory === cat ? "active" : ""}`}
                  onClick={() => setActiveCategory(cat)}
                >
                  {cat}
                </button>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ===== FEATURED FORECAST + RECOMMENDATIONS ===== */}
      <section style={{ padding: "40px 48px", maxWidth: 1400, margin: "0 auto" }}>
        <div className="search-forecast-grid">
          <div className="forecast-column">
            <div className="forecast-card animate-scale-in">
              <div className="forecast-card-header">
                <div className="forecast-card-title">
                  {featured.emoji} Premium Rice Market Forecast
                </div>
                <span
                  className={`trending-price-change ${featured.change >= 0 ? "up" : "down"}`}
                >
                  {featured.change >= 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                  &nbsp;{featured.change >= 0 ? "+" : ""}{featured.change}%
                </span>
              </div>
              <div className="forecast-metrics">
                <div className="forecast-metric">
                  <span className="forecast-metric-label">Current Price</span>
                  <span className="forecast-metric-value current">
                    ₱{featured.currentPrice.toFixed(2)}
                  </span>
                </div>
                <div className="forecast-metric">
                  <span className="forecast-metric-label">Predicted Price</span>
                  <span className="forecast-metric-value predicted">
                    ₱{featured.predictedPrice.toFixed(2)}
                  </span>
                </div>
                <div className="forecast-metric">
                  <span className="forecast-metric-label">Confidence</span>
                  <span className="forecast-metric-value confidence">
                    {featured.confidence}%
                  </span>
                </div>
              </div>
              <ForecastChart data={featured.chartData} height={260} />
            </div>
          </div>

          <aside className="recommended-column">
            <div className="recommended-panel">
              <div className="recommended-panel-header">
                Recommended
              </div>
              <div className="recommended-list">
                {filteredProducts.slice(0, 6).map((p) => (
                  <div className="recommended-item" key={p.id}>
                    <div className="recommended-left">
                      <div className="recommended-emoji">{p.emoji}</div>
                      <div>
                        <div className="recommended-name">{p.name}</div>
                        <div className="recommended-sub">₱{p.currentPrice.toFixed(2)}</div>
                      </div>
                    </div>
                    <div className={`recommended-change ${p.change >= 0 ? 'up' : 'down'}`}>
                      {p.change >= 0 ? `+${p.change}%` : `${p.change}%`}
                    </div>
                  </div>
                ))}
              </div>
              <a href="#" className="view-trends-btn" style={{ marginTop: 12, display: 'block' }}>
                View More →
              </a>
            </div>
          </aside>
        </div>
      </section>

      {/* ===== ALL PRODUCTS GRID ===== */}
      <section className="products-section">
        <div className="products-section-header">
          <h2 className="products-section-title">All Products</h2>
          <a href="#" className="view-all-link">
            View All <ChevronRight size={16} />
          </a>
        </div>
        <div className="products-grid">
          {filteredProducts.map((product) => (
            <ProductCard
              key={product.id}
              id={product.id}
              name={product.name}
              emoji={product.emoji}
              currentPrice={product.currentPrice}
              predictedPrice={product.predictedPrice}
              sparklineData={product.sparklineData}
            />
          ))}
        </div>
        {filteredProducts.length === 0 && (
          <div
            style={{
              textAlign: "center",
              padding: 60,
              color: "var(--text-gray)",
              fontSize: "1.1rem",
            }}
          >
            No products found matching &quot;{searchQuery}&quot;
          </div>
        )}
      </section>

      <Footer />
    </>
  );
};

export default SearchPage;
