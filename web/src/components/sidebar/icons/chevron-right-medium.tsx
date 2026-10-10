import type { SVGProps } from "react";

export const ChevronRightMediumIcon = (props: SVGProps<SVGSVGElement>) => {
    return (
        <svg
            width="24px"
            height="24px"
            viewBox="0.625 0 24 24"
            xmlns="http://www.w3.org/2000/svg"
            fontSize="13px"
            {...props}
        >
            <path
                d="M9.5 18.25L15.75 12L9.5 5.75"
                fontSize="13px"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.75"
                strokeLinecap="round"
                strokeLinejoin="round"
            />
        </svg>
    );
};
