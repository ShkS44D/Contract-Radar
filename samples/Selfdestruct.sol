// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

// Intentionally unsafe. EIP-6780 limits deletion but not Ether transfer.
contract Selfdestruct {
    constructor() payable {}

    function close(address payable recipient) external {
        selfdestruct(recipient);
    }
}
