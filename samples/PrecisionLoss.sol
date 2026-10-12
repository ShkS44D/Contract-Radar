// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

// Intentionally inaccurate: integer truncation occurs before multiplication.
contract PrecisionLoss {
    function quote(uint256 amount, uint256 rate) external pure returns (uint256) {
        return (amount / 100) * rate;
    }
}
