import type { SVGProps } from "react";

export const MagnifierIcon = (props: SVGProps<SVGSVGElement>) => {
    return (
        <svg
            width="16px"
            height="16px"
            viewBox="0 0 16 16"
            xmlns="http://www.w3.org/2000/svg"
            fontSize="13px"
            {...props}
        >
            <path
                d="M13.334 13.334L10.751 10.751M10.751 10.751C11.626 9.877 12.167 8.669 12.167 7.334C12.167 4.664 10.002 2.501 7.334 2.501C4.664 2.501 2.501 4.664 2.501 7.334C2.501 10.002 4.664 12.167 7.334 12.167C8.669 12.167 9.877 11.626 10.751 10.751Z"
                fontSize="13px"
                fill="none"
                stroke="currentColor"
                strokeWidth="1"
                strokeLinecap="round"
                strokeLinejoin="round"
            />
        </svg>
    );
};
