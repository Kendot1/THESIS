"use client";
import { useState, useEffect, useRef } from "react";
import Header from "../components/Header";
import Footer from "../components/Footer";
import {
  Database,
  Brain,
  LineChart as LineChartIcon,
  BarChart3,
  Layers,
  Lightbulb,
} from "lucide-react";

const stats = [
  { label: "Products Tracked", value: 12, suffix: "+" },
  { label: "Market Sources", value: 5, suffix: "+" },
  { label: "Accuracy Rate", value: 95, suffix: "%" },
  { label: "Weekly Updates", value: 52, suffix: "/yr" },
];

const methodologySteps = [
  {
    step: 1,
    title: "Data Preparation",
    description:
      "The dataset is cleaned, standardized, and organized by date to ensure consistent and reliable price records for modeling.",
    icon: Database,
  },
  {
    step: 2,
    title: "Feature Engineering",
    description:
      "Lag values, rolling statistics, and seasonal indicators are generated to capture price trends and patterns over time.",
    icon: Layers,
  },
  {
    step: 3,
    title: "Hybrid Model Training",
    description:
      "LSTM learns temporal price movements, while LightGBM models feature relationships and refines predictions for higher accuracy.",
    icon: Brain,
  },
  {
    step: 4,
    title: "Forecasting & Insights",
    description:
      "The system generates real-time price predictions and provides insights based on learned patterns from historical data.",
    icon: Lightbulb,
  },
];

const benchmarks = [
  {
    title: "Training Classification",
    badge: "95% Accuracy",
    description:
      "During initial model training, our classifier achieved high accuracy and solid recall on historical labeled data.",
    detail:
      "The model is validated on held-out data to ensure the trend signal is learned and not only memorized.",
    icon: LineChartIcon,
  },
  {
    title: "Mean Absolute Percentage Error",
    badge: "3.8% MAPE",
    description:
      "The ensemble records low average percentage errors across test products for week-ahead forecasts.",
    detail:
      "MAPE stays consistently low across vegetables, fish, and staple products under weekly evaluation.",
    icon: Database,
  },
  {
    title: "Forecast Window",
    badge: "Daily · Weekly · Monthly",
    description:
      "We provide hourly predictions up to five days ahead to help planning and decisions.",
    detail:
      "Forecast output balances practical planning horizon and confidence stability for short-term use.",
    icon: BarChart3,
  },
  {
    title: "Response Time",
    badge: "5-15s",
    description:
      "Model ensemble and inference pipeline are optimized for fast prediction latency.",
    detail:
      "Prediction requests are processed quickly so users can iterate product checks without waiting.",
    icon: Brain,
  },
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
  const [activeBenchmark, setActiveBenchmark] = useState(0);
  const [activeStep, setActiveStep] = useState(methodologySteps[0].step);
  const ActiveBenchmarkIcon = benchmarks[activeBenchmark].icon;

  return (
    <>
      <Header />

      {/* ===== ABOUT HERO ===== */}
      <section className="about-hero">
        <div className="about-hero-wave" />
        <div style={{ position: "relative", zIndex: 2 }}>
          <h1 className="animate-fade-in-up">About US</h1>
          {/* <p className="animate-fade-in-up delay-100">
            Lorem ipsum dolor sit amet. Et error dolor aut deserunt voluptas sit amet sit
            natus quia et possibilia velit.
          </p> */}
        </div>
      </section>
      {/* ===== MODEL DETAILS & PERFORMANCE ===== */}
      <section className="model-section">
        <div className="methodology-content">
          <h2 className="methodology-title animate-fade-in-up">MODEL DETAILS & PERFORMANCE</h2>
          <p className="methodology-description animate-fade-in-up delay-100">
            FOODCAST uses a hybrid modeling approach: an LSTM network to capture temporal
            dynamics and a LightGBM model to learn feature interactions. The ensemble
            combines both outputs to improve short-term price forecasting.
          </p>

          <div className="model-metrics">
            {/* <div className="metric-card">
              <div className="metric-label">Overall Accuracy</div>
              <div className="metric-value">95%</div>
              <div className="metric-note">Week-ahead classification accuracy</div>
            </div> */}
            <div className="metric-card">
              <div className="metric-label">Mean Absolute Percentage Error</div>
              <div className="metric-value">~3.8%</div>
              <div className="metric-note">Average across tracked products</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">Model Type</div>
              <div className="metric-value">LSTM + LightGBM</div>
              <div className="metric-note">Temporal + tree-based feature model</div>
            </div>
          </div>

          {/* System Benchmarks (visual cards) */}
          <div className="bench-grid animate-fade-in-up delay-200">
            {benchmarks.map((benchmark, index) => {
              const Icon = benchmark.icon;
              const isActive = activeBenchmark === index;
              return (
                <button
                  type="button"
                  key={benchmark.title}
                  className={`bench-card ${isActive ? "active" : ""}`}
                  onClick={() => setActiveBenchmark(index)}
                  onMouseEnter={() => setActiveBenchmark(index)}
                  onFocus={() => setActiveBenchmark(index)}
                  aria-pressed={isActive}
                >
                  <div className="bench-icon">
                    <Icon size={20} />
                  </div>
                  <div className="bench-badge">{benchmark.badge}</div>
                  <h4 className="bench-title">{benchmark.title}</h4>
                  <p className="bench-desc">{benchmark.description}</p>
                </button>
              );
            })}
          </div>

        

          {/* <h3 className="methodology-title small animate-fade-in-up delay-200">Automated vs No-Automation: Example Comparison</h3>
          

          <div className="comparison-card animate-fade-in-up delay-300">
            <table className="comparison-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Actual</th>
                  <th>No-Auto Pred.</th>
                  <th>Automated Pred.</th>
                  <th>No-Auto Error</th>
                  <th>Automated Error</th>
                </tr>
              </thead>
              <tbody>
                {[
                  { d: '2026-03-01', a: 50.0, n: 51.2, m: 49.6 },
                  { d: '2026-03-02', a: 49.5, n: 51.2, m: 49.8 },
                  { d: '2026-03-03', a: 50.8, n: 51.2, m: 50.2 },
                  { d: '2026-03-04', a: 51.0, n: 51.2, m: 50.9 },
                  { d: '2026-03-05', a: 50.4, n: 51.2, m: 50.1 },
                ].map((row) => {
                  const noErr = Math.abs((row.n - row.a) / row.a) * 100;
                  const autoErr = Math.abs((row.m - row.a) / row.a) * 100;
                  return (
                    <tr key={row.d}>
                      <td>{row.d}</td>
                      <td>₱{row.a.toFixed(2)}</td>
                      <td>₱{row.n.toFixed(2)}</td>
                      <td>₱{row.m.toFixed(2)}</td>
                      <td className={noErr <= autoErr ? 'error-badge worse' : 'error-badge'}>
                        {noErr.toFixed(1)}%
                      </td>
                      <td className={autoErr <= noErr ? 'error-badge better' : 'error-badge'}>
                        {autoErr.toFixed(1)}%
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <div className="comparison-legend">
              <span className="legend-item"><span className="dot better"/> Automated (lower error)</span>
              <span className="legend-item"><span className="dot worse"/> No-Auto baseline</span>
            </div>
          </div> */}
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
              FoodCast is an AI-powered agri-fisheries price forecasting system designed to predict daily, weekly, and monthly price movements of essential food products across NCR. It analyzes historical market data to generate accurate forecasts, identify trends, and provide insights into the factors influencing price changes.
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

      {/* ===== METHODOLOGY TIMELINE ===== */}
      <section className="methodology-section">
        <div className="methodology-content">
          <h2 className="methodology-title animate-fade-in-up">METHODOLOGY</h2>
          <p className="methodology-description animate-fade-in-up delay-100">
            AI-Based Forecasting and Market Analysis of Agri-Fishery Food Prices in NCR Markets
            using Algorithms.
          </p>

          <div className="methodology-timeline">
            {methodologySteps.map((item, index) => {
              const Icon = item.icon;
              const delayClass = `delay-${(index + 2) * 100}`;
              const isActive = activeStep === item.step;
              return (
                <div
                  className={`timeline-item animate-fade-in-up ${delayClass} ${isActive ? "active" : ""}`}
                  key={item.step}
                  onClick={() => setActiveStep(item.step)}
                  onMouseEnter={() => setActiveStep(item.step)}
                  onFocus={() => setActiveStep(item.step)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setActiveStep(item.step);
                    }
                  }}
                  role="button"
                  tabIndex={0}
                  aria-pressed={isActive}
                >
                  {/* Connector line (hidden for last item) */}
                  {index < methodologySteps.length - 1 && (
                    <div className="timeline-connector" />
                  )}

                  {/* Step number circle */}
                  <div className="timeline-node">
                    <span className="timeline-step-number">{item.step}</span>
                  </div>

                  {/* Content card */}
                  <div className="timeline-card">
                    <div className="timeline-card-icon">
                      <Icon size={22} />
                    </div>
                    <div className="timeline-card-body">
                      <h3>{item.title}</h3>
                      <p>{item.description}</p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      <Footer />
    </>
  );
};

export default AboutPage;
