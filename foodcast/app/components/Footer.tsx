import Link from "next/link";

const Footer = () => {
  return (
    <footer className="footer">
      <div className="footer-content">
        <div className="footer-brand">
          <div className="footer-logo">FOODCAST</div>
          <p>
            AI-Based Forecasting and Market Analysis of Agri-Fishery Food Prices in NCR Markets using Algorithms.
          </p>
          <p style={{ marginTop: 12, fontSize: "0.75rem", opacity: 0.5 }}>
            © 2026 AgriTech Food Forecast. All rights reserved.
          </p>
        </div>
        <div className="footer-nav">
          <h4>Navigation</h4>
          <ul>
            <li><Link href="/">Home</Link></li>
            <li><Link href="/Search">Search</Link></li>
            <li><Link href="/About">About</Link></li>
            <li><Link href="/Resources">Resources</Link></li>
          </ul>
        </div>
      </div>
      <div className="footer-divider" />
      <div className="footer-bottom">
        FOODCAST — Empowering smarter decisions with AI-driven food price forecasting.
      </div>
    </footer>
  );
};

export default Footer;
