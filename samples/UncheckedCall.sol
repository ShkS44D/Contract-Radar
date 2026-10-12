// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

// Intentionally vulnerable: low-level call failure is ignored.
contract UncheckedCall {
    function forward(address payable recipient) external payable {
        recipient.call{value: msg.value}("");
    }
}
