import type { SVGProps } from "react";

export const MascotAskIcon = (props: SVGProps<SVGSVGElement>) => {
    return (
        <svg
            width="24px"
            height="24px"
            viewBox="0 0 24 24"
            xmlns="http://www.w3.org/2000/svg"
            fontSize="13px"
            {...props}
        >
            <path
                d="M14.19 3.27C13.38 3.12 12.57 3.04 11.71 3.04C6.37 3.04 3.09 6.09 3.09 10.8V22.02L8.26 18.28H18.9C20.02 18.28 20.91 17.38 20.91 16.27V11.09"
                fontSize="13px"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.75"
                strokeLinecap="round"
                strokeLinejoin="round"
            />
            <rect x="7.29" y="8.79" width="2.3" height="4.31" rx="1.15" fontSize="13px" fill="currentColor" />
            <rect x="12.46" y="8.79" width="2.3" height="4.31" rx="1.15" fontSize="13px" fill="currentColor" />
            <path d="M19.6 0.25C20.31 3.31 20.79 3.79 23.85 4.5C20.79 5.21 20.31 5.69 19.6 8.75C18.89 5.69 18.41 5.21 15.35 4.5C18.41 3.79 18.89 3.31 19.6 0.25Z" fontSize="13px" fill="currentColor" />
        </svg>
    );
};
