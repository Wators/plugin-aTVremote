<?php

/* This file is part of Jeedom.
*
* Jeedom is free software: you can redistribute it and/or modify
* it under the terms of the GNU General Public License as published by
* the Free Software Foundation, either version 3 of the License, or
* (at your option) any later version.
*
* Jeedom is distributed in the hope that it will be useful,
* but WITHOUT ANY WARRANTY; without even the implied warranty of
* MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
* GNU General Public License for more details.
*
* You should have received a copy of the GNU General Public License
* along with Jeedom. If not, see <http://www.gnu.org/licenses/>.
*/

require_once dirname(__FILE__) . "/../../../../core/php/core.inc.php";

if (!jeedom::apiAccess(init('apikey'), 'aTVremote')) {
	echo __('Vous n\'etes pas autorisé à effectuer cette action', __FILE__);
	die();
}

if (init('test') != '') {
	echo 'OK';
	die();
}
$result = json_decode(file_get_contents("php://input"), true);
if (!is_array($result)) {
	log::add('aTVremote', 'debug', 'Format Invalide');
	die();
}

if (isset($result['devices'])) {
	foreach ($result['devices'] as $key => $datas) {
		$explode = explode('_',$key);
		$key = $explode[0];
		if (!isset($datas['id']) || !isset($datas['model'])) {
			continue;
		}
		$logical_id = $key;
		$aTVremote=aTVremote::byLogicalId($logical_id, 'aTVremote');
		if (!is_object($aTVremote)) {
			$aTVremote= aTVremote::createFromDef($datas);
			if (!is_object($aTVremote)) {
				log::add('aTVremote', 'debug', __('Aucun équipement trouvé pour : ', __FILE__) . secureXSS($datas['sid']));
				continue;
			}
			sleep(2);
			event::add('jeedom::alert', array(
				'level' => 'warning',
				'page' => 'aTVremote',
				'message' => '',
			));
			event::add('aTVremote::includeDevice', $aTVremote->getId());
		}
		if (!$aTVremote->getIsEnable()) {
			continue;
		}
		foreach ($aTVremote->getCmd('info') as $cmd) {
			$logicalId = $cmd->getLogicalId();
			if ($logicalId == '') {
				continue;
			}
			$path = explode('::', $logicalId);
			$value = $datas;
			foreach ($path as $key) {
				if (!isset($value[$key])) {
					continue (2);
				}
				$value = $value[$key];
				if (!is_array($value) && strpos($value, 'toggle') !== false && $cmd->getSubType() == 'binary') {
					$value = $cmd->execCmd();
					$value = ($value != 0) ? 0 : 1;
				}
			}
			if (!is_array($value)) {
				if ($cmd->getSubType() == 'numeric') {
					$value = round($value, 2);
				}
				$cmd->event($value);
			}
		}
	}
}

?>
