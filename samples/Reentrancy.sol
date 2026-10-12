// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

// Intentionally vulnerable. Never deploy this educational contract.
contract Reentrancy {
    mapping(address => uint256) public balances;

    function deposit() external payable {
        balances[msg.sender] += msg.value;
    }

    function withdraw(uint256 amount) external {
        require(balances[msg.sender] >= amount, "Insufficient balance");
        (bool success,) = msg.sender.call{value: amount}("");
        require(success, "Transfer failed");
        balances[msg.sender] -= amount; // Effect occurs after callback opportunity.
    }
}
