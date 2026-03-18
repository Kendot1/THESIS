"use client";
import { useState, useEffect, useRef } from "react";
import Header from "../components/Header";
import Footer from "../components/Footer";
import {
  Database,
  Brain,
  LineChart as LineChartIcon,
  BarChart3,
  Shield,
  Zap,
  Target,
  Award,
} from "lucide-react";

const stats = [
  { label: "Products Tracked", value: 12, suffix: "+" },
  { label: "Market Sources", value: 5, suffix: "+" },
  { label: "Accuracy Rate", value: 95, suffix: "%" },
  { label: "Weekly Updates", value: 52, suffix: "/yr" },
];

function AnimatedCounter({ target, suffix }: { target: number; suffix: string }) {
  const [count, setCount] = useState(0);
  const ref = useRef<HTMLDivElement>(null);
  const [hasAnimated, setHasAnimated] = useState(false);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !hasAnimated) {
          setHasAnimated(true);
          let start = 0;
          const duration = 2000;
          const increment = target / (duration / 16);
          const timer = setInterval(() => {
            start += increment;
            if (start >= target) {
              setCount(target);
              clearInterval(timer);
            } else {
              setCount(Math.floor(start));
            }
          }, 16);
        }
      },
      { threshold: 0.5 }
    );
    if (ref.current) observer.observe(ref.current);
    return () => observer.disconnect();
  }, [target, hasAnimated]);

  return (
    <div ref={ref} className="about-stat-value">
      {count}{suffix}
    </div>
  );
}

const AboutPage = () => {
  return (
    <>
      <Header />

      {/* ===== ABOUT HERO ===== */}
      <section className="about-hero">
        <div className="about-hero-wave" />
        <div style={{ position: "relative", zIndex: 2 }}>
          <h1 className="animate-fade-in-up">About US</h1>
          <p className="animate-fade-in-up delay-100">
            Lorem ipsum dolor sit amet. Et error dolor aut deserunt voluptas sit amet sit
            natus quia et possibilia velit.
          </p>
        </div>
      </section>

      {/* ===== WHAT IS FOODCAST? ===== */}
      <div className="about-content">
        <div className="about-what animate-fade-in-up">
          <div className="about-what-icon">
            <BarChart3 size={48} color="var(--primary-green)" />
          </div>
          <div className="about-what-text">
            <h2>What is FOODCAST?</h2>
            <p>
              Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor
              incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud
              exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure
              dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur.
              Qua aliqua pharum elit, consequat sit, enim inventore id rerum quasi aut iure quos autem
              aliquid ut doh consectetur aut consequetur sit.
            </p>
          </div>
        </div>

        {/* ===== STATS COUNTERS ===== */}
        <div className="about-stats">
          {stats.map((stat) => (
            <div className="about-stat-card" key={stat.label}>
              <div className="about-stat-label">{stat.label}</div>
              <AnimatedCounter target={stat.value} suffix={stat.suffix} />
            </div>
          ))}
        </div>
      </div>

      {/* ===== METHODOLOGY ===== */}
      <section className="methodology-section">
        <div className="methodology-content">
          <h2 className="methodology-title animate-fade-in-up">METHODOLOGY</h2>
          <p className="methodology-description animate-fade-in-up delay-100">
            AI-Based Forecasting and Market Analysis of Agri-Fishery Food Prices in NCR Markets
            using Algorithms.
          </p>
          <div className="methodology-grid">
            <div className="methodology-card animate-fade-in-up delay-200">
              <h3>
                <Database size={20} />
                Data Collection
              </h3>
              <p>
                Historical price data is collected from verified government sources and NCR market
                monitoring systems, covering multiple product categories.
              </p>
            </div>
            <div className="methodology-card animate-fade-in-up delay-300">
              <h3>
                <Brain size={20} />
                AI Model Training
              </h3>
              <p>
                Machine learning models are trained on cleaned and preprocessed data using regression
                and time-series analysis techniques.
              </p>
            </div>
            <div className="methodology-card animate-fade-in-up delay-400">
              <h3>
                <LineChartIcon size={20} />
                Forecasting
              </h3>
              <p>
                The trained models generate weekly price forecasts with confidence intervals, enabling
                stakeholders to make data-driven decisions.
              </p>
            </div>
          </div>
        </div>
      </section>

      <Footer />
    </>
  );
};

export default AboutPage;
