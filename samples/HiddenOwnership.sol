// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

// Intentionally vulnerable: ownership mutation and untrusted delegated execution.
contract HiddenOwnership {
    address public owner;

    constructor() {
        owner = msg.sender;
    }

    function sync(address next) external {
        owner = next;
    }

    function execute(address target, bytes calldata data) external returns (bytes memory) {
        (bool success, bytes memory result) = target.delegatecall(data);
        require(success, "Delegatecall failed");
        return result;
    }
}
