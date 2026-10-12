// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

// Intentionally vulnerable: a malicious intermediary can pass the origin check.
contract TxOrigin {
    address public immutable owner;

    constructor() payable {
        owner = msg.sender;
    }

    function withdraw(address payable recipient) external {
        require(tx.origin == owner, "Owner only");
        recipient.transfer(address(this).balance);
    }
}
