interface WaveDividerProps {
  from?: string;
  to?: string;
  flip?: boolean;
}

const WaveDivider = ({
  from = "#0B3D2E",
  to = "#FDFBF7",
  flip = false,
}: WaveDividerProps) => {
  return (
    <div
      className={`relative w-full overflow-hidden leading-[0] ${flip ? "rotate-180" : ""
        }`}
      aria-hidden="true"
    >
      <svg
        viewBox="0 0 1440 80"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        preserveAspectRatio="none"
        className="w-full h-[50px] sm:h-[70px] lg:h-[90px]"
      >
        <path
          d="M0 40C240 100 480 0 720 60C960 120 1200 20 1440 80V120H0V40Z"
          fill={to}
        />
        <path
          d="M0 60C240 120 480 20 720 80C960 140 1200 40 1440 100V120H0V60Z"
          fill={to}
          fillOpacity="0.5"
        />
        <rect width="1440" height="80" fill={from} fillOpacity="0" />
      </svg>
    </div>
  );
};

export default WaveDivider;
