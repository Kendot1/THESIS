"use client";
import { useEffect, useRef, useState } from "react";
import Header from "../components/Header";
import Footer from "../components/Footer";
import Link from "next/link";
import { FileText, ExternalLink, Download, BookOpen } from "lucide-react";

const resources = [
  {
    title: "Weekly Price Report",
    description: "Access the latest weekly price reports for NCR Agri-Fishery markets.",
    icon: <FileText size={24} />,
    link: "#",
  },
  {
    title: "Data Sources",
    description: "Learn about the government and institutional sources for our market data.",
    icon: <ExternalLink size={24} />,
    link: "#",
  },
  {
    title: "Download Datasets",
    description: "Download historical price datasets used in our forecasting models.",
    icon: <Download size={24} />,
    link: "#",
  },
  {
    title: "Research Papers",
    description: "Read the academic research papers behind our forecasting methodology.",
    icon: <BookOpen size={24} />,
    link: "#",
  },
];

function AnimatedResourceCard({ resource, index }: { resource: any; index: number }) {
  const [isVisible, setIsVisible] = useState(false);
  const ref = useRef<HTMLAnchorElement>(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          setIsVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.2, rootMargin: "50px" }
    );
    if (ref.current) observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);

  return (
    <Link
      ref={ref}
      href={resource.link}
      className={`product-card ${isVisible ? "animate-fade-in-up" : ""}`}
      style={{
        padding: 28,
        display: "flex",
        flexDirection: "column",
        gap: 12,
        opacity: isVisible ? 1 : 0,
        transform: isVisible ? "translateY(0)" : "translateY(30px)",
        transition: `opacity 0.6s ease ${(index % 2) * 0.2}s, transform 0.6s ease ${(index % 2) * 0.2}s`,
      }}
    >
      <div
        style={{
          width: 52,
          height: 52,
          borderRadius: "var(--radius-md)",
          background: "var(--bg-light-green)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--primary-dark)",
        }}
      >
        {resource.icon}
      </div>
      <h3
        style={{
          fontFamily: "'Poppins', sans-serif",
          fontWeight: 700,
          fontSize: "1.1rem",
          color: "var(--text-dark)",
        }}
      >
        {resource.title}
      </h3>
      <p style={{ color: "var(--text-gray)", fontSize: "0.9rem", lineHeight: 1.6 }}>
        {resource.description}
      </p>
    </Link>
  );
}

const ResourcesPage = () => {
  return (
    <>
      <Header />

      <section className="search-hero" style={{ paddingBottom: 100 }}>
        <div className="search-hero-wave" />
        <div style={{ position: "relative", zIndex: 2 }}>
          <h1 className="animate-fade-in-up">Resources</h1>
          <p className="animate-fade-in-up delay-100">
            Access data, reports, and research related to FOODCAST.
          </p>
        </div>
      </section>

      <section style={{ padding: "60px 48px 80px", maxWidth: 1000, margin: "0 auto", minHeight: "80vh" }}>
        {/* Placeholder div to push content down so we can test scrolling if needed */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 24 }}>
          {resources.map((resource, index) => (
            <AnimatedResourceCard key={resource.title} resource={resource} index={index} />
          ))}
        </div>
      </section>

      <Footer />
    </>
  );
};

export default ResourcesPage;
