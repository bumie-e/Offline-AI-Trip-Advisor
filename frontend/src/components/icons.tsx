import type { SVGProps } from 'react'

/** Small stroke icons, inlined so they work offline and add no dependency. */
type IconProps = SVGProps<SVGSVGElement>

function Icon({ children, className = 'size-4', ...props }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={className}
      {...props}
    >
      {children}
    </svg>
  )
}

export const CompassIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="m15.5 8.5-2 5-5 2 2-5z" />
  </Icon>
)

export const BookmarkIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M6 4h12v16l-6-4-6 4z" />
  </Icon>
)

export const PinIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21z" />
    <circle cx="12" cy="9.5" r="2.5" />
  </Icon>
)

export const CalendarIcon = (p: IconProps) => (
  <Icon {...p}>
    <rect x="3.5" y="5" width="17" height="15" rx="2" />
    <path d="M3.5 10h17M8 3v4M16 3v4" />
  </Icon>
)

export const UsersIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="9" cy="8" r="3.5" />
    <path d="M2.5 20a6.5 6.5 0 0 1 13 0M16 4.5a3.5 3.5 0 0 1 0 7M18 14.5a6.5 6.5 0 0 1 3.5 5.5" />
  </Icon>
)

export const CarIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 16.5V12l2-5.5h12l2 5.5v4.5zM4 12h16" />
    <circle cx="7.5" cy="16.5" r="1.8" />
    <circle cx="16.5" cy="16.5" r="1.8" />
  </Icon>
)

export const PlaneIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M17.8 19.2 16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2z" />
  </Icon>
)

export const TrainIcon = (p: IconProps) => (
  <Icon {...p}>
    <rect x="5" y="3" width="14" height="14" rx="3" />
    <path d="M5 11h14M8 21l2-4M16 21l-2-4" />
  </Icon>
)

export const WalkIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="13" cy="4.5" r="1.5" />
    <path d="m9 21 2.5-6.5L14 16v5M8 11l3-3.5 3 1 2 3.5M11.5 14.5 12 9" />
  </Icon>
)

export const ClockIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 2" />
  </Icon>
)

export const CheckIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="m5 12.5 4.5 4.5L19 7.5" />
  </Icon>
)

export const ArrowLeftIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M19 12H5M11 18l-6-6 6-6" />
  </Icon>
)

export const ArrowRightIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M5 12h14M13 6l6 6-6 6" />
  </Icon>
)

export const ChevronRightIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="m9 6 6 6-6 6" />
  </Icon>
)

export const CloudOffIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3 3l18 18M8 7.3A6 6 0 0 1 17.6 10 4 4 0 0 1 20 17M17 18H7a5 5 0 0 1-2.2-9.5" />
  </Icon>
)

export const OfflineReadyIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 3v11M7.5 9.5 12 14l4.5-4.5M5 17v2.5h14V17" />
  </Icon>
)

export const RainIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M7 15a4.5 4.5 0 0 1-.4-9A6 6 0 0 1 18 8a3.5 3.5 0 0 1-.5 7z" />
    <path d="m8 18-1 2.5M12 18l-1 2.5M16 18l-1 2.5" />
  </Icon>
)

export const AlertIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 4 2.5 20h19z" />
    <path d="M12 10v4.5M12 17.5v.01" />
  </Icon>
)

export const RoadIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M8 3 4 21M16 3l4 18M12 4v3M12 11v3M12 18v2" />
  </Icon>
)

export const InfoIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 11v5.5M12 7.5v.01" />
  </Icon>
)

export const LandmarkIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3 20h18M5 20v-8M19 20v-8M9.5 20v-8M14.5 20v-8M2.5 12 12 4l9.5 8z" />
  </Icon>
)

export const SparkIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6" />
  </Icon>
)

export const ExternalIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M14 4h6v6M20 4l-9 9M18 14v6H4V6h6" />
  </Icon>
)

export const MinusIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M5 12h14" />
  </Icon>
)

export const PlusIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 5v14M5 12h14" />
  </Icon>
)
